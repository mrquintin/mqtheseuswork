import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { AlertTriangle, CheckCircle2, Layers2, ShieldX } from "lucide-react";

import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";
import { canWrite } from "@/lib/roles";
import {
  evaluateSocialPostGates,
  evaluateSubstackPostGatesForPost,
  socialGateContext,
  substackGateContext,
} from "@/lib/socialPosting";

import { killOutboundAction } from "../actions";
import { SubstackReviewBlock, XReviewBlock } from "./review-blocks";

export const dynamic = "force-dynamic";

type Params = Promise<{ id: string }>;

export default async function SocialPostReviewPage({ params }: { params: Params }) {
  const founder = await getFounder();
  if (!founder) redirect("/login");
  if (!canWrite(founder.role)) redirect("/dashboard");

  const { id } = await params;
  const post = await db.socialPost.findFirst({
    where: { id, organizationId: founder.organizationId },
  });
  if (!post) notFound();

  const [gates, sibling] = await Promise.all([
    post.platform === "substack"
      ? evaluateSubstackPostGatesForPost(post, await substackGateContext(founder.organizationId))
      : Promise.resolve(evaluateSocialPostGates(post, await socialGateContext(founder.organizationId))),
    post.bundleId
      ? db.socialPost.findFirst({
          where: {
            bundleId: post.bundleId,
            id: { not: post.id },
            organizationId: founder.organizationId,
          },
          select: { id: true, platform: true, status: true },
        })
      : Promise.resolve(null),
  ]);

  const reviewPost = {
    id: post.id,
    body: post.body,
    subject: post.subject,
    markdownBody: post.markdownBody,
    status: post.status,
    externalId: post.externalId,
    postedAt: post.postedAt?.toISOString() || null,
  };

  return (
    <main style={{ display: "grid", gap: "1rem", margin: "0 auto", maxWidth: 1220, padding: "1.5rem 1rem 3rem" }}>
      <header style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", justifyContent: "space-between" }}>
        <div>
          <Link className="mono" href="/social" style={{ color: "var(--amber-dim)", fontSize: "0.65rem", textDecoration: "none" }}>
            Social queue
          </Link>
          <h1 style={{ color: "var(--amber)", fontFamily: "'Cinzel Decorative', 'Cinzel', serif", margin: "0.25rem 0 0" }}>
            {post.platform === "substack" ? post.subject || "Substack draft" : "X draft"}
          </h1>
          <p className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.65rem", margin: "0.35rem 0 0" }}>
            {post.source} / {post.platform.toUpperCase()} / {post.createdAt.toISOString()}
          </p>
        </div>
        <StatusBadge status={post.status} />
      </header>

      <section
        className="portal-card"
        style={{
          borderColor: "rgba(185, 92, 92, 0.8)",
          display: "grid",
          gap: "0.65rem",
          padding: "0.85rem",
        }}
      >
        <div className="mono" style={{ color: "var(--parchment-dim)", fontSize: "0.66rem" }}>
          Global kill switch disables every outbound channel.
        </div>
        <form action={killOutboundAction}>
          <button
            className="btn"
            data-testid="social-kill-button"
            style={{ borderColor: "rgba(185, 92, 92, 0.95)", color: "var(--ember)" }}
            type="submit"
          >
            <ShieldX aria-hidden="true" size={16} /> KILL - disable all outbound
          </button>
        </form>
      </section>

      {sibling ? (
        <section className="portal-card" style={{ alignItems: "center", borderColor: "rgba(205, 151, 67, 0.45)", display: "flex", flexWrap: "wrap", gap: "0.5rem", padding: "0.75rem" }}>
          <Layers2 aria-hidden="true" color="var(--amber)" size={15} />
          <span className="mono" style={{ color: "var(--amber-dim)", fontSize: "0.66rem", letterSpacing: "0.12em", textTransform: "uppercase" }}>
            Bundled sibling:
          </span>
          <Link href={`/social/${sibling.id}`} style={{ color: "var(--gold)" }}>
            {sibling.platform.toUpperCase()} is {sibling.status}
          </Link>
        </section>
      ) : null}

      <GateStrip failures={gates} platform={post.platform} />

      {post.failureReason ? (
        <p role="alert" style={{ color: "var(--ember)", margin: 0 }}>
          {post.failureReason}
        </p>
      ) : null}

      {post.platform === "substack" ? (
        <SubstackReviewBlock post={reviewPost} />
      ) : (
        <XReviewBlock post={reviewPost} sourceUrl={firstHttpsUrl(post.body) || sourceUrl(post.source, post.sourceId)} />
      )}
    </main>
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
