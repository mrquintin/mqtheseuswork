import type { Metadata } from "next";

import PublicHeader from "@/components/PublicHeader";
import RespondForm from "@/components/RespondForm";
import { getFounder } from "@/lib/auth";
import { listPublishedConclusions } from "@/lib/conclusionsRead";

export const dynamic = "force-dynamic";
export const revalidate = 60;

export const metadata: Metadata = {
  title: "Responses",
};

export default async function ResponsesPage() {
  const [founder, conclusions] = await Promise.all([getFounder(), listPublishedConclusions()]);

  return (
    <>
      <PublicHeader authed={Boolean(founder)} />
      <main className="public-container">
        <h1 className="public-title">Structured responses</h1>
        <p className="public-muted public-lede">
          Default: no inline comments. Responses are moderated, structured, and appear as a separate section when approved.
          Notable responses can be promoted to <strong>engaged</strong>, which triggers internal review of the conclusion.
        </p>

        <RespondForm conclusions={conclusions} />
      </main>
    </>
  );
}
