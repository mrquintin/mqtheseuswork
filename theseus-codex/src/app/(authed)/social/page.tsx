import Link from "next/link";
import { redirect } from "next/navigation";
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  Layers2,
  Save,
  Send,
  ShieldX,
  XCircle,
} from "lucide-react";

import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";
import { canWrite } from "@/lib/roles";
import {
  evaluateSocialPostGates,
  evaluateSubstackPostGatesForPost,
  SOCIAL_KILL_KEY,
  socialGateContext,
  SUBSTACK_KILL_KEY,
  substackGateContext,
  weightedXLength,
} from "@/lib/socialPosting";

import {
  approveAndPostAction,
  bulkApproveSelectedAction,
  bulkRejectSelectedAction,
  killOutboundAction,
  rejectPostAction,
  saveDraftAction,
} from "./actions";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{
  bundle?: string;
  platform?: string;
  status?: string;
}>;

const platformFilters = [
  { label: "All", value: "all" },
  { label: "X", value: "x" },
  { label: "Substack", value: "substack" },
] as const;

const statusFilters = [
  { label: "All", value: "all" },
  { label: "Draft", value: "draft" },
  { label: "Approved", value: "approved" },
  { label: "Posted", value: "posted" },
  { label: "Rejected", value: "rejected" },
  { label: "Failed", value: "failed" },
] as const;

export default async function SocialPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const founder = await getFounder();
  if (!founder) redirect("/login");
  if (!canWrite(founder.role)) redirect("/dashboard");

  const params = await searchParams;
  const platform = normalizeFilter(params.platform, ["x", "substack"]);
  const status = normalizeFilter(params.status, ["draft", "approved", "posted", "rejected", "failed"]);
  const highlightedBundle = isUuid(params.bundle || "") ? params.bundle || "" : "";

  const where = {
    organizationId: founder.organizationId,
    ...(platform === "all" ? {} : { platform }),
    ...(status === "all" ? {} : { status }),
  };

  const [posts, xCtx, substackCtx, xKillState, substackKillState] = await Promise.all([
    db.socialPost.findMany({
      where,
      orderBy: [{ createdAt: "desc" }],
      take: 200,
    }),
    socialGateContext(founder.organizationId),
    substackGateContext(founder.organizationId),
    db.operatorState.findUnique({
      where: {
        organizationId_key: {
          organizationId: founder.organizationId,
          key: SOCIAL_KILL_KEY,
        },
      },
      select: { updatedAt: true, value: true },
    }),
    db.operatorState.findUnique({
      where: {
        organizationId_key: {
          organizationId: founder.organizationId,
          key: SUBSTACK_KILL_KEY,
        },
      },
      select: { updatedAt: true, value: true },
    }),
  ]);

  const rows = await Promise.all(
    posts.map(async (post) => ({
      post,
      gates:
        post.platform === "substack"
          ? await evaluateSubstackPostGatesForPost(post, substackCtx)
          : evaluateSocialPostGates(post, xCtx),
    })),
  );
  const groups = groupRows(rows);

  return (
    <main className="social-queue-shell" style={{ display: "grid", gap: "1rem", margin: "0 auto", maxWidth: 1220, padding: "1.5rem 1rem 3rem" }}>
      <section>
        <p className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.68rem", letterSpacing: "0.2em", margin: 0, textTransform: "uppercase" }}>
          Founder operator console
        </p>
        <h1 style={{ color: "var(--amber)", fontFamily: "'Cinzel Decorative', 'Cinzel', serif", margin: "0.2rem 0 0" }}>
          Outbound publish panel
        </h1>
      </section>

      <section
        className="portal-card"
        style={{
          borderColor: xCtx.killSwitchEngaged || substackCtx.killSwitchEngaged ? "rgba(185, 92, 92, 0.8)" : "rgba(232, 225, 211, 0.14)",
          display: "grid",
          gap: "0.8rem",
          padding: "1rem",
        }}
      >
        <div className="mono" style={{ color: "var(--parchment-dim)", display: "flex", flexWrap: "wrap", fontSize: "0.68rem", gap: "0.5rem 1rem" }}>
          <span>X env: {xCtx.postingEnabled ? "enabled" : "disabled"}</span>
          <span>X OAuth: {xCtx.oauthRefreshConfigured ? "configured" : "missing"}</span>
          <span>X 24h budget: {xCtx.postsLast24h}/{xCtx.dailyMax}</span>
          <span>X kill: {xCtx.killSwitchEngaged ? "engaged" : "clear"}</span>
          <span>Substack env: {substackCtx.postingEnabled ? "enabled" : "disabled"}</span>
          <span>Substack identity: {substackCtx.identityConfigured ? "configured" : "missing"}</span>
          <span>Substack kill: {substackCtx.killSwitchEngaged ? "engaged" : "clear"}</span>
          {xKillState?.updatedAt ? <span>X kill updated: {xKillState.updatedAt.toISOString()}</span> : null}
          {substackKillState?.updatedAt ? <span>Substack kill updated: {substackKillState.updatedAt.toISOString()}</span> : null}
        </div>
        <form action={killOutboundAction}>
          <button
            className="btn"
            data-testid="social-kill-button"
            style={{
              borderColor: "rgba(185, 92, 92, 0.95)",
              color: "var(--ember)",
            }}
            type="submit"
          >
            <ShieldX aria-hidden="true" size={16} /> KILL - disable all outbound
          </button>
        </form>
      </section>

      <section className="portal-card" style={{ display: "grid", gap: "0.8rem", padding: "0.9rem 1rem" }}>
        <FilterRow
          active={platform}
          ariaLabel="Platform filter"
          items={platformFilters}
          param="platform"
          params={params}
        />
        <FilterRow
          active={status}
          ariaLabel="Status filter"
          items={statusFilters}
          param="status"
          params={params}
        />
      </section>

      <form
        action={bulkApproveSelectedAction}
        aria-label="Bulk social post actions"
        className="bulk-action-bar portal-card"
        id="bulk-social-actions"
        style={{
          alignItems: "center",
          borderColor: "rgba(205, 151, 67, 0.6)",
          display: "none",
          flexWrap: "wrap",
          gap: "0.55rem",
          padding: "0.75rem",
          position: "sticky",
          top: "0.75rem",
          zIndex: 5,
        }}
      >
        <span className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.66rem", letterSpacing: "0.14em", textTransform: "uppercase" }}>
          Selected drafts
        </span>
        <button className="btn" data-testid="bulk-approve-selected" formAction={bulkApproveSelectedAction} type="submit">
          <Send aria-hidden="true" size={15} /> Approve all selected (Drafts only)
        </button>
        <button className="btn" data-testid="bulk-reject-selected" formAction={bulkRejectSelectedAction} style={{ color: "var(--ember)" }} type="submit">
          <XCircle aria-hidden="true" size={15} /> Reject all selected (Drafts only)
        </button>
      </form>

      <section aria-label="Unified outbound queue" style={{ display: "grid", gap: "0.8rem" }}>
        {groups.length === 0 ? (
          <div className="portal-card" style={{ color: "var(--parchment-dim)", padding: "1rem" }}>
            No outbound posts match these filters.
          </div>
        ) : (
          groups.map((group) => (
            <QueueGroup highlighted={group.bundleId === highlightedBundle} key={group.key} group={group} />
          ))
        )}
      </section>

      <style>{`
        .social-queue-shell:has(input[name="postId"]:checked) .bulk-action-bar {
          display: flex !important;
        }
      `}</style>
    </main>
  );
}

function QueueGroup({
  group,
  highlighted,
}: {
  group: QueueGroupModel;
  highlighted: boolean;
}) {
  const bundled = Boolean(group.bundleId && group.rows.length > 1);
  return (
    <section
      className="portal-card"
      data-bundle-id={group.bundleId || undefined}
      data-testid={bundled ? "social-bundle-group" : "social-single-group"}
      style={{
        borderColor: highlighted ? "rgba(205, 151, 67, 0.8)" : bundled ? "rgba(205, 151, 67, 0.38)" : "rgba(232, 225, 211, 0.14)",
        display: "grid",
        gap: "0.75rem",
        padding: "0.85rem",
      }}
    >
      {bundled ? (
        <div className="mono" style={{ alignItems: "center", color: "var(--amber-dim)", display: "flex", flexWrap: "wrap", fontSize: "0.64rem", gap: "0.45rem", letterSpacing: "0.14em", textTransform: "uppercase" }}>
          <Layers2 aria-hidden="true" size={14} /> Bundle {shortId(group.bundleId || "")} · act on the sibling before this leaves the queue
        </div>
      ) : null}
      {group.rows.map(({ gates, post }) => (
        <QueueRow gates={gates} key={post.id} post={post} sibling={group.rows.find((row) => row.post.id !== post.id)?.post || null} />
      ))}
    </section>
  );
}

function QueueRow({
  gates,
  post,
  sibling,
}: {
  gates: Array<{ code: string; detail: string }>;
  post: RowPost;
  sibling: RowPost | null;
}) {
  const isDraft = post.status === "draft";
  const isPosted = post.status === "posted";
  const title = post.platform === "substack" ? post.subject || "Substack draft" : "X draft";
  return (
    <article
      data-social-post-id={post.id}
      data-testid="social-queue-row"
      style={{
        border: "1px solid rgba(232, 225, 211, 0.12)",
        borderRadius: 6,
        display: "grid",
        gap: "0.75rem",
        padding: "0.85rem",
      }}
    >
      <div style={{ alignItems: "start", display: "grid", gap: "0.75rem", gridTemplateColumns: "auto minmax(0, 1fr) auto" }}>
        <input
          aria-label={`Select ${post.platform} ${post.status} post`}
          disabled={!isDraft}
          form="bulk-social-actions"
          name="postId"
          style={{ marginTop: "0.25rem" }}
          type="checkbox"
          value={post.id}
        />
        <div style={{ minWidth: 0 }}>
          <div className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.64rem" }}>
            {post.source} / {post.platform.toUpperCase()} / {post.createdAt.toISOString()}
          </div>
          <h2 style={{ color: "var(--parchment)", fontFamily: "'Cinzel', serif", fontSize: "1rem", letterSpacing: "0.06em", margin: "0.25rem 0 0" }}>
            <Link href={`/social/${post.id}`} style={{ color: "inherit", textDecoration: "none" }}>
              {title}
            </Link>
          </h2>
          <SourceLink body={post.body} source={post.source} sourceId={post.sourceId} />
        </div>
        <StatusBadge status={post.status} />
      </div>

      {post.platform === "x" && !isPosted ? (
        <form style={{ display: "grid", gap: "0.65rem" }}>
          <input name="postId" type="hidden" value={post.id} />
          <textarea
            aria-label={`Edit X post ${post.id}`}
            defaultValue={post.body}
            name="body"
            rows={4}
            style={textareaStyle}
          />
          <div className="mono" style={{ color: weightedXLength(post.body) > 280 ? "var(--ember)" : "var(--parchment-dim)", fontSize: "0.66rem" }}>
            {weightedXLength(post.body)}/280 weighted chars
          </div>
          <GateStrip failures={gates} platform={post.platform} />
          <RowActions postId={post.id} save />
        </form>
      ) : isPosted ? (
        <div style={{ display: "grid", gap: "0.65rem" }}>
          <p style={{ color: "var(--parchment)", lineHeight: 1.55, margin: 0, whiteSpace: "pre-wrap" }}>
            {post.platform === "substack" ? post.body : post.body}
          </p>
          {post.platform === "substack" && post.markdownBody ? (
            <p style={{ color: "var(--parchment-dim)", lineHeight: 1.5, margin: 0 }}>
              {excerpt(post.markdownBody, 320)}
            </p>
          ) : null}
          <GateStrip failures={gates} platform={post.platform} />
        </div>
      ) : (
        <form style={{ display: "grid", gap: "0.65rem" }}>
          <p style={{ color: "var(--parchment)", lineHeight: 1.55, margin: 0, whiteSpace: "pre-wrap" }}>
            {post.body}
          </p>
          {post.platform === "substack" && post.markdownBody ? (
            <p style={{ color: "var(--parchment-dim)", lineHeight: 1.5, margin: 0 }}>
              {excerpt(post.markdownBody, 320)}
            </p>
          ) : null}
          <GateStrip failures={gates} platform={post.platform} />
          <RowActions postId={post.id} />
        </form>
      )}

      {sibling && post.status === "posted" && sibling.status !== "posted" ? (
        <p className="mono" role="status" style={{ color: "var(--amber)", fontSize: "0.66rem", margin: 0 }}>
          Bundled sibling still needs review: {sibling.platform.toUpperCase()} is {sibling.status}.
        </p>
      ) : null}

      {post.failureReason ? (
        <p role="alert" style={{ color: "var(--ember)", margin: 0 }}>
          {post.failureReason}
        </p>
      ) : null}

      {isPosted ? (
        <div className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.68rem" }}>
          externalId: {post.externalId || (post.platform === "substack" ? "substack-email-to-post" : "n/a")} / postedAt: {post.postedAt?.toISOString() || "n/a"}
        </div>
      ) : null}
    </article>
  );
}

function RowActions({ postId, save = false }: { postId: string; save?: boolean }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.55rem" }}>
      <input name="postId" type="hidden" value={postId} />
      {save ? (
        <button className="btn" formAction={saveDraftAction} type="submit">
          <Save aria-hidden="true" size={15} /> Save edit
        </button>
      ) : null}
      <button className="btn" data-testid="social-approve-post" formAction={approveAndPostAction} type="submit">
        <Send aria-hidden="true" size={15} /> Approve & post
      </button>
      <button className="btn" formAction={rejectPostAction} style={{ color: "var(--ember)" }} type="submit">
        <XCircle aria-hidden="true" size={15} /> Reject
      </button>
      <Link className="btn" href={`/social/${postId}`} style={{ textDecoration: "none" }}>
        <ExternalLink aria-hidden="true" size={15} /> Review
      </Link>
    </div>
  );
}

function FilterRow({
  active,
  ariaLabel,
  items,
  param,
  params,
}: {
  active: string;
  ariaLabel: string;
  items: ReadonlyArray<{ label: string; value: string }>;
  param: "platform" | "status";
  params: { bundle?: string; platform?: string; status?: string };
}) {
  return (
    <nav aria-label={ariaLabel} style={{ display: "flex", flexWrap: "wrap", gap: "0.45rem" }}>
      {items.map((item) => (
        <FilterChip
          active={active === item.value}
          href={filterHref(params, param, item.value)}
          key={item.value}
          label={item.label}
        />
      ))}
    </nav>
  );
}

function FilterChip({ active, href, label }: { active: boolean; href: string; label: string }) {
  return (
    <Link
      aria-current={active ? "page" : undefined}
      className="btn"
      href={href}
      style={{
        background: active ? "rgba(205, 151, 67, 0.16)" : "transparent",
        borderColor: active ? "rgba(205, 151, 67, 0.7)" : "rgba(232, 225, 211, 0.16)",
        minHeight: "2rem",
        textDecoration: "none",
      }}
    >
      {label}
    </Link>
  );
}

function SourceLink({ body, source, sourceId }: { body: string; source: string; sourceId: string | null }) {
  const url = firstHttpsUrl(body) || sourceUrl(source, sourceId);
  if (!url) {
    return (
      <span className="mono" style={{ color: "var(--ember)", fontSize: "0.68rem" }}>
        No source link
      </span>
    );
  }
  return (
    <a className="mono" href={url} rel="noopener noreferrer" style={{ color: "var(--gold)", fontSize: "0.68rem" }} target="_blank">
      {url}
    </a>
  );
}

function StatusBadge({ status }: { status: string }) {
  const posted = status === "posted";
  const failed = status === "failed" || status === "rejected";
  return (
    <span
      className="mono"
      style={{
        alignItems: "center",
        border: `1px solid ${posted ? "rgba(126, 166, 133, 0.6)" : failed ? "rgba(185, 92, 92, 0.65)" : "rgba(205, 151, 67, 0.6)"}`,
        borderRadius: 999,
        color: posted ? "rgba(184, 231, 192, 0.95)" : failed ? "var(--ember)" : "var(--amber)",
        display: "inline-flex",
        fontSize: "0.62rem",
        gap: "0.35rem",
        padding: "0.18rem 0.45rem",
        textTransform: "uppercase",
      }}
    >
      {posted ? <CheckCircle2 aria-hidden="true" size={13} /> : failed ? <AlertTriangle aria-hidden="true" size={13} /> : null}
      {status}
    </span>
  );
}

function GateStrip({ failures, platform }: { failures: Array<{ code: string; detail: string }>; platform: string }) {
  const codes =
    platform === "substack"
      ? ["NOT_CONFIGURED", "DISABLED", "CONTENT_REJECTED", "SOURCE_REJECTED", "NOT_APPROVED"]
      : ["NOT_CONFIGURED", "DISABLED", "DAILY_BUDGET_EXCEEDED", "CONTENT_REJECTED", "CITATION_REQUIRED", "NOT_APPROVED"];
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
      {codes.map((code) => {
        const failure = failures.find((item) => item.code === code);
        return (
          <span
            className="mono"
            data-gate-code={code}
            data-gate-state={failure ? "fail" : "pass"}
            key={code}
            title={failure?.detail || "Pass"}
            style={{
              border: `1px solid ${failure ? "rgba(185, 92, 92, 0.65)" : "rgba(126, 166, 133, 0.55)"}`,
              borderRadius: 999,
              color: failure ? "var(--ember)" : "rgba(160, 211, 170, 0.9)",
              fontSize: "0.58rem",
              padding: "0.16rem 0.4rem",
            }}
          >
            {code}
          </span>
        );
      })}
    </div>
  );
}

type RowWithGates = {
  gates: Array<{ code: string; detail: string }>;
  post: RowPost;
};

type RowPost = {
  id: string;
  organizationId: string;
  createdAt: Date;
  source: string;
  sourceId: string | null;
  platform: string;
  bundleId: string | null;
  body: string;
  markdownBody: string | null;
  subject: string | null;
  status: string;
  approvedBy: string | null;
  postedAt: Date | null;
  externalId: string | null;
  failureReason: string | null;
};

type QueueGroupModel = {
  bundleId: string | null;
  key: string;
  rows: RowWithGates[];
};

function groupRows(rows: RowWithGates[]): QueueGroupModel[] {
  const groups = new Map<string, QueueGroupModel>();
  rows.forEach((row) => {
    const key = row.post.bundleId || row.post.id;
    const existing = groups.get(key);
    if (existing) {
      existing.rows.push(row);
      return;
    }
    groups.set(key, {
      bundleId: row.post.bundleId,
      key,
      rows: [row],
    });
  });
  return Array.from(groups.values()).map((group) => ({
    ...group,
    rows: group.rows.sort((left, right) => left.post.platform.localeCompare(right.post.platform)),
  }));
}

function filterHref(
  params: { bundle?: string; platform?: string; status?: string },
  param: "platform" | "status",
  value: string,
): string {
  const next = new URLSearchParams();
  const platform = param === "platform" ? value : normalizeFilter(params.platform, ["x", "substack"]);
  const status = param === "status" ? value : normalizeFilter(params.status, ["draft", "approved", "posted", "rejected", "failed"]);
  if (platform !== "all") next.set("platform", platform);
  if (status !== "all") next.set("status", status);
  if (params.bundle && isUuid(params.bundle)) next.set("bundle", params.bundle);
  const query = next.toString();
  return query ? `/social?${query}` : "/social";
}

function normalizeFilter(value: string | undefined, allowed: string[]): string {
  return value && allowed.includes(value) ? value : "all";
}

function firstHttpsUrl(body: string): string | null {
  const match = body.match(/https:\/\/[^\s<>()]+/i);
  return match?.[0] || null;
}

function sourceUrl(source: string, sourceId: string | null): string | null {
  if (!sourceId) return null;
  if (source === "currents.opinion") return `/currents/${sourceId}`;
  if (source === "session") return `/sessions/${sourceId}`;
  if (source.startsWith("upload")) return `/upload/${sourceId}`;
  return null;
}

function excerpt(text: string, limit: number): string {
  const compact = text.replace(/\s+/g, " ").trim();
  if (compact.length <= limit) return compact;
  return `${compact.slice(0, limit - 3).trimEnd()}...`;
}

function shortId(id: string): string {
  return id.slice(0, 8);
}

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}

const textareaStyle = {
  background: "rgba(0,0,0,0.22)",
  border: "1px solid rgba(232, 225, 211, 0.16)",
  borderRadius: 6,
  color: "var(--parchment)",
  lineHeight: 1.45,
  padding: "0.75rem",
  resize: "vertical" as const,
};
