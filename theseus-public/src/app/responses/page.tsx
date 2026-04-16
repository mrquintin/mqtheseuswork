import type { Metadata } from "next";

import { bundle } from "@/lib/bundle";

import RespondForm from "@/components/RespondForm";

export const metadata: Metadata = {
  title: "Responses",
};

export default function ResponsesPage() {
  return (
    <main className="container">
      <h1 style={{ marginTop: 0 }}>Structured responses</h1>
      <p className="muted" style={{ maxWidth: "75ch" }}>
        Default: no inline comments. Responses are moderated, structured, and appear as a separate section when approved.
        Notable responses can be promoted to <strong>engaged</strong>, which triggers internal review of the conclusion.
      </p>

      <div style={{ marginTop: "1.25rem" }}>
        <RespondForm conclusions={bundle.conclusions} />
      </div>
    </main>
  );
}
