"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import ExplorerCanvas, {
  type ExplorerEdge,
  type ExplorerPoint,
} from "@/components/ExplorerCanvas";
import ExplorerEmptyState, {
  type ExplorerIndexStatus,
} from "@/components/ExplorerEmptyState";
import ExplorerSavedViews from "@/components/ExplorerSavedViews";
import ExplorerSelectionPane from "@/components/ExplorerSelectionPane";
import ExplorerToolbar from "@/components/ExplorerToolbar";
import PageKeymap from "@/components/PageKeymap";
import { type HotkeyBinding } from "@/lib/hotkeys";
import { clearReduceCache, reduce, type ReducedPoint } from "@/lib/dimReduce";
import {
  DEFAULT_VIEWPORT,
  ZOOM_MAX,
  ZOOM_MIN,
  clampViewport,
  decodeExplorerState,
  deleteSavedView,
  encodeExplorerState,
  loadSavedViews,
  saveView,
  updateSavedView,
  viewportsEqual,
  type ExplorerState,
  type ExplorerViewport,
  type SavedView,
} from "@/lib/explorerState";

interface RawIndex {
  points: Array<
    ExplorerPoint & {
      embedding?: number[];
      // The legacy `/api/conclusions/embeddings` endpoint returns
      // pre-projected coordinates instead of raw vectors. We accept
      // both shapes here so the new Explorer keeps working as the
      // backend rolls out the richer payload.
      x?: number;
      y?: number;
    }
  >;
  edges?: ExplorerEdge[];
  embeddingDim?: number;
  status?: "ready" | "warming-up";
  embeddedCount?: number;
  totalCount?: number;
  error?: string | null;
  canRebuild?: boolean;
}

interface LegacyProjection {
  conclusions: Array<{
    id: string;
    text: string;
    topicHint: string;
    confidenceTier: string;
    x: number;
    y: number;
  }>;
  axes: Array<{ label: string; varianceExplained: number }>;
  status?: "ready" | "warming-up";
  embeddedCount?: number;
  totalCount?: number;
  error?: string | null;
  canRebuild?: boolean;
}

function adaptLegacyProjection(legacy: LegacyProjection): {
  points: ExplorerPoint[];
  preProjected: ReducedPoint[];
} {
  return {
    points: legacy.conclusions.map((c) => ({
      id: c.id,
      text: c.text,
      topicHint: c.topicHint || "",
      confidenceTier: c.confidenceTier || "open",
      methods: [],
      isPrivate: false,
    })),
    preProjected: legacy.conclusions.map((c) => ({ x: c.x, y: c.y })),
  };
}

const ZOOM_STEP = 1.4;

export default function ExplorerPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [points, setPoints] = useState<ExplorerPoint[]>([]);
  const [embeddings, setEmbeddings] = useState<number[][]>([]);
  const [preProjected, setPreProjected] = useState<ReducedPoint[] | null>(null);
  const [edges, setEdges] = useState<ExplorerEdge[]>([]);
  const [loadingState, setLoadingState] = useState<
    "loading" | "ready" | "warming" | "error"
  >("loading");
  const [indexStats, setIndexStats] = useState<{ embedded: number; total: number }>({
    embedded: 0,
    total: 0,
  });
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [canRebuild, setCanRebuild] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [savedViews, setSavedViews] = useState<SavedView[]>([]);
  const [recenterTo, setRecenterTo] = useState<string[] | null>(null);

  // ── Decode URL state ────────────────────────────────────────────-
  const decoded: ExplorerState = useMemo(() => {
    const params = new URLSearchParams(searchParams?.toString() ?? "");
    return decodeExplorerState(params);
  }, [searchParams]);

  // The viewport is held in local state during a gesture so a wheel-
  // zoom doesn't spam router.replace; it's flushed to the URL once the
  // gesture settles (see the debounce effect below). Every other field
  // round-trips through the URL directly.
  const [liveViewport, setLiveViewport] = useState<ExplorerViewport>(
    decoded.viewport,
  );
  const urlViewportKey = `${decoded.viewport.cx},${decoded.viewport.cy},${decoded.viewport.scale}`;
  useEffect(() => {
    // Adopt the URL viewport whenever it changes from outside this
    // component (paste, back button, saved-view selection).
    setLiveViewport(decoded.viewport);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlViewportKey]);

  // The state every handler reads: URL-decoded, but with the live
  // viewport patched in so it's never stale mid-gesture.
  const state: ExplorerState = useMemo(
    () => ({ ...decoded, viewport: liveViewport }),
    [decoded, liveViewport],
  );

  const selectionSet = useMemo(() => new Set(state.selection), [state.selection]);

  // ── Push state to URL ────────────────────────────────────────────
  const writeState = useCallback(
    (next: ExplorerState) => {
      const params = encodeExplorerState(next);
      const query = params.toString();
      const path = query ? `/explorer?${query}` : "/explorer";
      router.replace(path, { scroll: false });
    },
    [router],
  );

  // Debounced viewport → URL flush. Keeps the gesture smooth, then
  // makes the resting view linkable ~220ms after it settles.
  useEffect(() => {
    if (viewportsEqual(liveViewport, decoded.viewport)) return;
    const timer = setTimeout(() => {
      writeState({ ...decoded, viewport: liveViewport });
    }, 220);
    return () => clearTimeout(timer);
  }, [liveViewport, decoded, writeState]);

  // ── Load saved views ────────────────────────────────────────────
  useEffect(() => {
    setSavedViews(loadSavedViews());
  }, []);

  // ── Fetch index ──────────────────────────────────────────────────
  const cancelledRef = useRef(false);
  const fetchIndex = useCallback(async () => {
    setLoadingState("loading");
    try {
      const res = await fetch("/api/conclusions/embeddings", { cache: "no-store" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `HTTP ${res.status}`);
      }
      const json = (await res.json()) as Partial<RawIndex> & Partial<LegacyProjection>;
      if (cancelledRef.current) return;

      setCanRebuild(Boolean(json.canRebuild));
      setIndexStats({
        embedded: json.embeddedCount ?? 0,
        total: json.totalCount ?? 0,
      });

      if (json.status === "warming-up") {
        setLoadingState("warming");
        return;
      }

      if (Array.isArray(json.points)) {
        // New richer payload.
        const indexed = json.points;
        const hasRawEmbeddings = indexed.every(
          (p) => Array.isArray(p.embedding) && p.embedding.length > 0,
        );
        setPoints(
          indexed.map((p) => ({
            id: p.id,
            text: p.text,
            topicHint: p.topicHint || "",
            confidenceTier: p.confidenceTier || "open",
            methods: Array.isArray(p.methods) ? p.methods : [],
            isPrivate: Boolean(p.isPrivate),
          })),
        );
        if (hasRawEmbeddings) {
          setEmbeddings(indexed.map((p) => p.embedding as number[]));
          setPreProjected(null);
        } else {
          setEmbeddings([]);
          setPreProjected(indexed.map((p) => ({ x: p.x ?? 0, y: p.y ?? 0 })));
        }
        setEdges(Array.isArray(json.edges) ? json.edges : []);
      } else if (Array.isArray(json.conclusions)) {
        // Legacy payload. Carry the projection through verbatim — we
        // can't switch reducers, but the UI degrades gracefully.
        const adapted = adaptLegacyProjection(json as LegacyProjection);
        setPoints(adapted.points);
        setEmbeddings([]);
        setPreProjected(adapted.preProjected);
        setEdges([]);
      } else {
        setPoints([]);
        setEmbeddings([]);
        setPreProjected(null);
        setEdges([]);
      }
      setLoadingState("ready");
    } catch (err) {
      if (cancelledRef.current) return;
      setErrorMessage((err as Error).message);
      setLoadingState("error");
    }
  }, []);

  useEffect(() => {
    cancelledRef.current = false;
    void fetchIndex();
    return () => {
      cancelledRef.current = true;
    };
  }, [fetchIndex]);

  // Rebuild = drop the client-side projection cache (the part of the
  // "index" the Explorer owns) and re-fetch. Gated to founders by
  // `canRebuild`; the API re-checks regardless.
  const onRebuild = useCallback(async () => {
    setRebuilding(true);
    try {
      clearReduceCache();
      await fetchIndex();
    } finally {
      if (!cancelledRef.current) setRebuilding(false);
    }
  }, [fetchIndex]);

  // ── Project ──────────────────────────────────────────────────────
  const projection = useMemo<ReducedPoint[]>(() => {
    if (preProjected) return preProjected;
    if (embeddings.length === 0) return [];
    return reduce(embeddings, state.reducer).points;
  }, [preProjected, embeddings, state.reducer]);

  // ── Handlers ────────────────────────────────────────────────────-
  const onChangeState = useCallback(
    (next: ExplorerState) => {
      // A state change that also moves the viewport must keep the
      // live-viewport mirror in sync, or the debounce effect will
      // immediately revert it.
      setLiveViewport(next.viewport);
      writeState(next);
    },
    [writeState],
  );

  const onViewportChange = useCallback((next: ExplorerViewport) => {
    setLiveViewport(next);
  }, []);

  const onLassoSelect = useCallback(
    (ids: string[]) => {
      writeState({ ...state, selection: ids, focused: null });
    },
    [state, writeState],
  );

  const onClearSelection = useCallback(() => {
    writeState({ ...state, selection: [], focused: null });
  }, [state, writeState]);

  const onPointClick = useCallback(
    (id: string) => {
      writeState({ ...state, focused: id });
    },
    [state, writeState],
  );

  const onSelectFocus = useCallback(
    (id: string | null) => {
      writeState({ ...state, focused: id });
    },
    [state, writeState],
  );

  const onShowNeighborhood = useCallback(
    (id: string) => {
      // Re-centre canvas on this point's region, dropping any prior
      // lasso selection so the founder can re-lasso freshly. The
      // focused conclusion stays open.
      setRecenterTo([id]);
      writeState({ ...state, selection: [], focused: id });
    },
    [state, writeState],
  );

  const onSaveView = useCallback(
    (label: string, description?: string) => {
      setSavedViews(saveView(label, state, description));
    },
    [state],
  );

  const onSelectSavedView = useCallback(
    (view: SavedView) => {
      const next = decodeExplorerState(new URLSearchParams(view.query));
      onChangeState(next);
    },
    [onChangeState],
  );

  const onDeleteSavedView = useCallback((id: string) => {
    setSavedViews(deleteSavedView(id));
  }, []);

  const onRenameSavedView = useCallback(
    (id: string, patch: { label?: string; description?: string }) => {
      setSavedViews(updateSavedView(id, patch));
    },
    [],
  );

  // ── Page keymap ──────────────────────────────────────────────────
  // Canvas interactions all have a keyboard equivalent so the Explorer
  // stays usable without a mouse: l = lasso hint, s = save view,
  // o = contradicts overlay, = / - = zoom, 0 = reset view.
  const explorerBindings = useMemo<HotkeyBinding[]>(
    () => [
      {
        chord: "l",
        description: "Lasso (drag on the canvas to select a region)",
        handler: () => {
          if (typeof window === "undefined") return;
          window.dispatchEvent(new CustomEvent("explorer:lasso-hint"));
        },
      },
      {
        chord: "s",
        description: "Save current view",
        handler: () => {
          if (typeof window === "undefined") return;
          const label = window.prompt("Save view as:");
          if (label && label.trim()) onSaveView(label.trim());
        },
      },
      {
        chord: "o",
        description: "Toggle contradicts overlay",
        handler: () => {
          onChangeState({
            ...state,
            overlays: { ...state.overlays, contradicts: !state.overlays.contradicts },
          });
        },
      },
      {
        chord: "=",
        description: "Zoom in",
        handler: () => {
          onChangeState({
            ...state,
            viewport: clampViewport({
              ...state.viewport,
              scale: Math.min(ZOOM_MAX, state.viewport.scale * ZOOM_STEP),
            }),
          });
        },
      },
      {
        chord: "-",
        description: "Zoom out",
        handler: () => {
          onChangeState({
            ...state,
            viewport: clampViewport({
              ...state.viewport,
              scale: Math.max(ZOOM_MIN, state.viewport.scale / ZOOM_STEP),
            }),
          });
        },
      },
      {
        chord: "0",
        description: "Reset zoom and pan",
        handler: () => {
          onChangeState({ ...state, viewport: { ...DEFAULT_VIEWPORT } });
        },
      },
    ],
    [onSaveView, onChangeState, state],
  );

  // ── Render guards ────────────────────────────────────────────────
  const indexDiagnostic = (status: ExplorerIndexStatus) => (
    <main style={pageStyle}>
      <Header />
      <ExplorerEmptyState
        status={status}
        embedded={indexStats.embedded}
        total={indexStats.total}
        message={errorMessage}
        canRebuild={canRebuild}
        onRebuild={onRebuild}
        rebuilding={rebuilding}
      />
    </main>
  );

  if (loadingState === "loading") return indexDiagnostic("loading");
  if (loadingState === "error") return indexDiagnostic("error");
  if (loadingState === "warming") return indexDiagnostic("warming");
  if (points.length < 3) return indexDiagnostic("empty");

  // Ready, but the index lags the conclusion count — show a non-
  // blocking stale banner above the canvas rather than hiding it.
  const isStale =
    indexStats.total > 0 && indexStats.embedded < indexStats.total;

  return (
    <main style={pageStyle}>
      <PageKeymap bindings={explorerBindings} label="Explorer" />
      <Header />
      {isStale ? (
        <div style={{ marginBottom: "0.75rem" }}>
          <ExplorerEmptyState
            status="stale"
            embedded={indexStats.embedded}
            total={indexStats.total}
            canRebuild={canRebuild}
            onRebuild={onRebuild}
            rebuilding={rebuilding}
          />
        </div>
      ) : null}
      <ExplorerToolbar
        state={state}
        onChange={onChangeState}
        onClearSelection={onClearSelection}
        selectionCount={selectionSet.size}
        totalCount={points.length}
      />
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr) 320px",
          gap: "0.85rem",
          alignItems: "start",
        }}
      >
        <ExplorerCanvas
          points={points}
          projection={projection}
          edges={edges}
          overlays={state.overlays}
          selection={selectionSet}
          focusedId={state.focused}
          onLassoSelect={onLassoSelect}
          onClearSelection={onClearSelection}
          onPointClick={onPointClick}
          recenterTo={recenterTo}
          viewport={state.viewport}
          onViewportChange={onViewportChange}
        />
        <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
          <ExplorerSelectionPane
            selection={selectionSet}
            points={points}
            projection={projection}
            edges={edges}
            focusedId={state.focused}
            onSelectFocus={onSelectFocus}
            onShowNeighborhood={onShowNeighborhood}
          />
          <ExplorerSavedViews
            savedViews={savedViews}
            onSave={onSaveView}
            onSelect={onSelectSavedView}
            onDelete={onDeleteSavedView}
            onRename={onRenameSavedView}
          />
        </div>
      </div>
    </main>
  );
}

function Header() {
  return (
    <>
      <h2
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--amber)",
          letterSpacing: "0.06em",
          fontSize: "1.2rem",
          margin: "0 0 0.4rem",
          fontWeight: 500,
        }}
      >
        Explorer
      </h2>
      <p
        style={{
          fontSize: "0.85rem",
          color: "var(--parchment-dim)",
          maxWidth: "44em",
          lineHeight: 1.5,
          margin: "0 0 1rem",
        }}
      >
        A 2-D projection of the firm&apos;s conclusion embeddings. Drag a
        lasso to select a region, scroll to zoom and shift-drag to pan,
        toggle overlays for contradictions or supports, click a point to open
        the conclusion. Every view — selection, overlays, zoom, pan — is a URL.
      </p>
    </>
  );
}

const pageStyle: React.CSSProperties = {
  maxWidth: "1280px",
  margin: "0 auto",
  padding: "1.5rem 2rem 2rem",
};
