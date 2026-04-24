"use client";

import type { PublicOpinion, PublicSource } from "@/lib/currentsTypes";
import { OpinionCard } from "../OpinionCard";
import { AuditTrail } from "./AuditTrail";
import { CopyLinkButton } from "./CopyLinkButton";
import { SourceDrawer } from "./SourceDrawer";

export function DetailClient({
  opinion,
  sources,
}: {
  opinion: PublicOpinion;
  sources: PublicSource[];
}) {
  return (
    <>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "0.4rem" }}>
        <CopyLinkButton opinionId={opinion.id} />
      </div>
      <OpinionCard op={opinion} />
      <div
        className="currents-detail-split"
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr) minmax(280px, 420px)",
          gap: "1.25rem",
          marginTop: "1.25rem",
          alignItems: "start",
        }}
      >
        <AuditTrail op={opinion} />
        <SourceDrawer citations={opinion.citations} sources={sources} />
      </div>
    </>
  );
}
