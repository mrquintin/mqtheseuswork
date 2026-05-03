import Link from "next/link";

import DetailClient from "@/app/currents/[id]/DetailClient";
import { getCurrent, getCurrentSources } from "@/lib/currentsApi";
import { getFounder } from "@/lib/auth";
import { canWrite } from "@/lib/roles";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function FounderCurrentDetailPage({ params }: PageProps) {
  const { id } = await params;
  const [opinion, sources, founder] = await Promise.all([
    getCurrent(id),
    getCurrentSources(id),
    getFounder(),
  ]);

  return (
    <main style={{ maxWidth: 1120, margin: "0 auto", padding: "1.5rem 1.25rem 4rem" }}>
      <Link
        className="mono"
        href="/founder-currents"
        style={{
          color: "var(--amber-dim)",
          display: "inline-block",
          fontSize: "0.72rem",
          marginBottom: "1rem",
          textDecoration: "none",
        }}
      >
        Back to founder currents
      </Link>
      <DetailClient
        canPublish={Boolean(founder && canWrite(founder.role))}
        opinion={opinion}
        sources={sources}
      />
    </main>
  );
}
