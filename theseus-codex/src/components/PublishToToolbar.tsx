"use client";

import { ChevronDown, FileText, Layers2, Send } from "lucide-react";
import { usePathname } from "next/navigation";

import {
  createBothDraftsFromArtifactAction,
  createSubstackDraftFromArtifactAction,
  createXDraftFromArtifactAction,
} from "@/app/(authed)/social/actions";

type ArtifactType = "session" | "upload" | "currents-opinion";

export default function PublishToToolbar({
  artifactType,
  artifactId,
  disabled = false,
}: {
  artifactType: ArtifactType;
  artifactId: string;
  disabled?: boolean;
}) {
  const pathname = usePathname() || "/dashboard";

  return (
    <details style={{ position: "relative" }}>
      <summary
        aria-disabled={disabled}
        className="btn"
        data-testid="publish-to-dropdown"
        style={{
          cursor: disabled ? "not-allowed" : "pointer",
          opacity: disabled ? 0.55 : 1,
          width: "max-content",
        }}
      >
        <Send aria-hidden="true" size={15} /> Publish to <ChevronDown aria-hidden="true" size={14} />
      </summary>
      {!disabled ? (
        <div
          className="portal-card"
          style={{
            background: "rgba(14, 10, 7, 0.98)",
            display: "grid",
            gap: "0.35rem",
            marginTop: "0.45rem",
            minWidth: "12rem",
            padding: "0.45rem",
            position: "absolute",
            right: 0,
            zIndex: 20,
          }}
        >
          <PublishForm
            action={createSubstackDraftFromArtifactAction}
            artifactId={artifactId}
            artifactType={artifactType}
            icon="substack"
            label="Substack"
            returnPath={pathname}
            testId="publish-to-substack"
          />
          <PublishForm
            action={createXDraftFromArtifactAction}
            artifactId={artifactId}
            artifactType={artifactType}
            icon="x"
            label="X"
            returnPath={pathname}
            testId="publish-to-x"
          />
          <PublishForm
            action={createBothDraftsFromArtifactAction}
            artifactId={artifactId}
            artifactType={artifactType}
            icon="both"
            label="Both"
            returnPath={pathname}
            testId="publish-to-both"
          />
        </div>
      ) : null}
    </details>
  );
}

function PublishForm({
  action,
  artifactId,
  artifactType,
  icon,
  label,
  returnPath,
  testId,
}: {
  action: (formData: FormData) => Promise<void>;
  artifactId: string;
  artifactType: ArtifactType;
  icon: "substack" | "x" | "both";
  label: string;
  returnPath: string;
  testId: string;
}) {
  const Icon = icon === "both" ? Layers2 : FileText;
  return (
    <form action={action}>
      <input name="artifactId" type="hidden" value={artifactId} />
      <input name="artifactType" type="hidden" value={artifactType} />
      <input name="returnPath" type="hidden" value={returnPath} />
      <button
        className="btn"
        data-testid={testId}
        style={{ justifyContent: "flex-start", width: "100%" }}
        type="submit"
      >
        <Icon aria-hidden="true" size={15} /> {label}
      </button>
    </form>
  );
}
