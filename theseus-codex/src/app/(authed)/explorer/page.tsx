"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
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
        <HealthPanel
          status="loading"
          embedded={warmupStats?.embedded ?? 0}
          total={warmupStats?.total ?? 0}
        />
      </main>
    );
  }
  if (loadingState === "error") {
    return (
      <main style={pageStyle}>
        <Header />
        <HealthPanel
          status="error"
          embedded={0}
          total={0}
          message={errorMessage}
        />
      </main>
    );
  }
  if (loadingState === "warming") {
    return (
      <main style={pageStyle}>
        <Header />
        <HealthPanel
          status="warming"
          embedded={warmupStats?.embedded ?? 0}
          total={warmupStats?.total ?? 0}
        />
      </main>
    );
  }
  if (points.length < 3) {
    return (
      <main style={pageStyle}>
        <Header />
        <HealthPanel status="empty" embedded={points.length} total={points.length} />
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
        lasso to select a region, toggle overlays for contradictions or
        supports, click a point to open the conclusion. Every view is a URL.
      </p>
    </>
  );
}

function HealthPanel({
  status,
  embedded,
  total,
  message,
}: {
  status: "loading" | "warming" | "empty" | "error";
  embedded: number;
  total: number;
  message?: string | null;
}) {
  const pct =
    total > 0 ? Math.max(0, Math.min(100, Math.round((embedded / total) * 100))) : 0;
  const tone =
    status === "error"
      ? "var(--ember)"
      : status === "loading"
        ? "var(--info)"
        : "var(--amber)";
  const heading =
    status === "loading"
      ? "Loading projection…"
      : status === "error"
        ? "Projection failed to load"
        : status === "warming"
          ? "Waiting for embeddings"
          : "Not enough embedded conclusions";

  return (
    <section
      className="portal-card"
      style={{
        padding: "1rem 1.1rem",
        borderLeft: `3px solid ${tone}`,
      }}
    >
      <div
        className="mono"
        style={{
          fontSize: "0.6rem",
          letterSpacing: "0.2em",
          textTransform: "uppercase",
          color: tone,
          marginBottom: "0.4rem",
        }}
      >
        Embedding health
      </div>
      <h3
        style={{
          margin: 0,
          fontFamily: "'EB Garamond', serif",
          fontSize: "1.05rem",
          color: "var(--parchment)",
          fontWeight: 500,
        }}
      >
        {heading}
      </h3>
      {status !== "loading" ? (
        <p
          style={{
            margin: "0.45rem 0 0",
            fontSize: "0.85rem",
            color: "var(--parchment-dim)",
            lineHeight: 1.5,
          }}
        >
          {status === "error" ? (
            <>The embeddings API returned an error: {message || "unknown"}.</>
          ) : status === "warming" ? (
            <>
              The Explorer activates once the firm has at least 3 embedded
              conclusions. The data shown elsewhere may look empty because
              embeddings have not yet been populated for these conclusions.
            </>
          ) : (
            <>
              The Explorer needs at least 3 conclusions to project. Add more
              uploads, or wait for the next ingest pass to embed existing
              conclusions.
            </>
          )}
        </p>
      ) : null}
      <div
        className="mono"
        style={{
          marginTop: "0.6rem",
          fontSize: "0.7rem",
          color: "var(--parchment)",
          letterSpacing: "0.08em",
          display: "flex",
          gap: "0.5rem",
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        <span>
          embedded {embedded}/{total}
          {total > 0 ? ` (${pct}%)` : ""}
        </span>
        {total > 0 ? (
          <span
            aria-hidden="true"
            style={{
              flex: "1 1 8rem",
              minWidth: "6rem",
              maxWidth: "12rem",
              height: 4,
              background: "var(--stone-mid)",
              borderRadius: 2,
              overflow: "hidden",
            }}
          >
            <span
              style={{
                display: "block",
                width: `${pct}%`,
                height: "100%",
                background: tone,
              }}
            />
          </span>
        ) : null}
      </div>
      {status === "warming" || status === "empty" ? (
        <div
          style={{
            marginTop: "0.75rem",
            display: "flex",
            gap: "0.5rem",
            flexWrap: "wrap",
          }}
        >
          <Link
            href="/upload"
            className="btn"
            style={{
              fontSize: "0.62rem",
              padding: "0.3rem 0.65rem",
              textDecoration: "none",
            }}
          >
            Add an upload
          </Link>
          <Link
            href="/ops"
            className="btn"
            style={{
              fontSize: "0.62rem",
              padding: "0.3rem 0.65rem",
              textDecoration: "none",
            }}
          >
            Open ops console
          </Link>
        </div>
      ) : null}
      {status === "error" ? (
        <div style={{ marginTop: "0.75rem" }}>
          <button
            type="button"
            className="btn"
            onClick={() => {
              if (typeof window !== "undefined") window.location.reload();
            }}
            style={{ fontSize: "0.62rem", padding: "0.3rem 0.65rem" }}
          >
            Retry
          </button>
        </div>
      ) : null}
    </section>
  );
}

const pageStyle: React.CSSProperties = {
  maxWidth: "1280px",
  margin: "0 auto",
  padding: "1.5rem 2rem 2rem",
};
