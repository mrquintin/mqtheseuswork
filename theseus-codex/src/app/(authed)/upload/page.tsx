import UploadForm from "@/components/UploadForm";
import { canWrite } from "@/lib/roles";
import { requireTenantContext } from "@/lib/tenant";

export default async function UploadPage() {
  const tenant = await requireTenantContext();
  if (!tenant) return null;
  if (!canWrite(tenant.role)) {
    return (
      <main
        style={{
          maxWidth: "640px",
          margin: "0 auto",
          padding: "4rem 2rem",
          textAlign: "center",
        }}
      >
        <h1
          style={{
            fontFamily: "'Cinzel', serif",
            fontSize: "1.35rem",
            letterSpacing: "0.06em",
            color: "var(--amber)",
            textShadow: "var(--glow-sm)",
            margin: 0,
          }}
        >
          Upload
        </h1>
        <p
          className="mono"
          style={{
            fontSize: "0.6rem",
            letterSpacing: "0.16em",
            textTransform: "uppercase",
            color: "var(--amber-dim)",
            marginTop: "0.5rem",
          }}
        >
          Read-only account
        </p>
        <p
          style={{
            fontFamily: "'EB Garamond', serif",
            fontSize: "1.05rem",
            color: "var(--parchment-dim)",
            marginTop: "2rem",
            lineHeight: 1.65,
          }}
        >
          Your account can read everything in the firm&apos;s Codex but
          cannot upload new material. Ask an admin in your organisation
          to upgrade you to <strong>founder</strong> if you need to
          contribute transcripts, sessions, or essays.
        </p>
      </main>
    );
  }
  return <UploadForm />;
}
