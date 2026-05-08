"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import ExplorerCanvas, {
  type ExplorerEdge,
  type ExplorerPoint,
} from "@/components/ExplorerCanvas";
import ExplorerSelectionPane from "@/components/ExplorerSelectionPane";
import ExplorerToolbar from "@/components/ExplorerToolbar";
import PageKeymap from "@/components/PageKeymap";
import { type HotkeyBinding } from "@/lib/hotkeys";
import { reduce, type ReducedPoint, type Reducer } from "@/lib/dimReduce";
import {
  DEFAULT_EXPLORER_STATE,
  decodeExplorerState,
  deleteSavedView,
  encodeExplorerState,
  loadSavedViews,
  saveView,
  type ExplorerState,
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
  const [warmupStats, setWarmupStats] = useState<{ embedded: number; total: number } | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [savedViews, setSavedViews] = useState<SavedView[]>([]);
  const [recenterTo, setRecenterTo] = useState<string[] | null>(null);

  // ── Decode URL state ────────────────────────────────────────────-
  const state: ExplorerState = useMemo(() => {
    const params = new URLSearchParams(searchParams?.toString() ?? "");
    return decodeExplorerState(params);
  }, [searchParams]);

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

  // ── Load saved views ────────────────────────────────────────────
  useEffect(() => {
    setSavedViews(loadSavedViews());
  }, []);

  // ── Fetch index ──────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoadingState("loading");
      try {
        const res = await fetch("/api/conclusions/embeddings");
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.error || `HTTP ${res.status}`);
        }
        const json = (await res.json()) as Partial<RawIndex> & Partial<LegacyProjection>;
        if (cancelled) return;

        if (json.status === "warming-up") {
          setLoadingState("warming");
          setWarmupStats({
            embedded: json.embeddedCount ?? 0,
            total: json.totalCount ?? 0,
          });
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
            setPreProjected(
              indexed.map((p) => ({ x: p.x ?? 0, y: p.y ?? 0 })),
            );
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
        if (cancelled) return;
        setErrorMessage((err as Error).message);
        setLoadingState("error");
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  // ── Project ──────────────────────────────────────────────────────
  const projection = useMemo<ReducedPoint[]>(() => {
    if (preProjected) return preProjected;
    if (embeddings.length === 0) return [];
    return reduce(embeddings, state.reducer).points;
  }, [preProjected, embeddings, state.reducer]);

  // ── Toolbar handlers ────────────────────────────────────────────-
  const onChangeState = useCallback(
    (next: ExplorerState) => {
      writeState(next);
    },
    [writeState],
  );

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
    (label: string) => {
      const updated = saveView(label, state);
      setSavedViews(updated);
    },
    [state],
  );

  const onSelectSavedView = useCallback(
    (view: SavedView) => {
      const next = decodeExplorerState(new URLSearchParams(view.query));
      writeState(next);
    },
    [writeState],
  );

  const onDeleteSavedView = useCallback((id: string) => {
    setSavedViews(deleteSavedView(id));
  }, []);

  // ── Page keymap ──────────────────────────────────────────────────
  // l = lasso (canvas drag is the only way today; we surface a toast
  // explaining the tool when l is pressed, and prep for a future
  // canvas-driven hotkey selection mode). s = save view. o = toggle
  // the contradicts overlay (the most-used overlay).
  const explorerBindings = useMemo<HotkeyBinding[]>(
    () => [
      {
        chord: "l",
        description: "Lasso (drag on the canvas to select a region)",
        handler: () => {
          if (typeof window === "undefined") return;
          // We surface a status hint; the canvas itself responds to
          // mouse drags. A future iteration can drive a keyboard-only
          // marquee — wiring is in place via the canvas ref.
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
    ],
    [onSaveView, onChangeState, state],
  );

  // ── Render guards ────────────────────────────────────────────────
  if (loadingState === "loading") {
    return (
      <main style={pageStyle}>
        <Header />
        <p style={dimNote}>Loading embedding projection…</p>
      </main>
    );
  }
  if (loadingState === "error") {
    return (
      <main style={pageStyle}>
        <Header />
        <p style={{ ...dimNote, color: "var(--ember)" }}>
          Failed to load projection: {errorMessage}
        </p>
      </main>
    );
  }
  if (loadingState === "warming") {
    return (
      <main style={pageStyle}>
        <Header />
        <p style={dimNote}>
          The semantic explorer activates after the firm has 3 embedded
          conclusions. Currently: {warmupStats?.embedded ?? 0}/
          {warmupStats?.total ?? 0}. Embeddings auto-populate as
          conclusions are created.
        </p>
      </main>
    );
  }
  if (points.length < 3) {
    return (
      <main style={pageStyle}>
        <Header />
        <p style={dimNote}>
          The semantic explorer is waiting for embedded conclusions.
        </p>
      </main>
    );
  }

  return (
    <main style={pageStyle}>
      <PageKeymap bindings={explorerBindings} label="Explorer" />
      <Header />
      <ExplorerToolbar
        state={state}
        onChange={onChangeState}
        onSaveView={onSaveView}
        onClearSelection={onClearSelection}
        savedViews={savedViews}
        onSelectSavedView={onSelectSavedView}
        onDeleteSavedView={onDeleteSavedView}
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
        />
        <ExplorerSelectionPane
          selection={selectionSet}
          points={points}
          projection={projection}
          edges={edges}
          focusedId={state.focused}
          onSelectFocus={onSelectFocus}
          onShowNeighborhood={onShowNeighborhood}
        />
      </div>
    </main>
  );
}

function Header() {
  return (
    <>
      <h1
        style={{
          fontFamily: "'Cinzel', serif",
          color: "var(--gold)",
          letterSpacing: "0.08em",
          margin: "0 0 0.5rem",
        }}
      >
        Semantic Explorer
      </h1>
      <p
        style={{
          fontFamily: "'EB Garamond', serif",
          fontStyle: "italic",
          fontSize: "1rem",
          color: "var(--parchment-dim)",
          maxWidth: "44em",
          lineHeight: 1.55,
          marginBottom: "1.5rem",
        }}
      >
        A navigation surface over your firm&apos;s belief geometry. Drag a
        lasso to select a region; toggle Contradicts to draw the geometric
        contradiction edges across the canvas; click a conclusion to pivot
        into its detail. Every view is a URL.
      </p>
    </>
  );
}

const pageStyle: React.CSSProperties = {
  maxWidth: "1280px",
  margin: "0 auto",
  padding: "2rem",
};

const dimNote: React.CSSProperties = {
  color: "var(--parchment-dim)",
  fontSize: "0.85rem",
};
