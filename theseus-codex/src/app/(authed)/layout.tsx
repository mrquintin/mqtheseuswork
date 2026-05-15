import { redirect } from "next/navigation";
import { getFounder } from "@/lib/auth";
import Nav from "@/components/Nav";
import SubNav from "@/components/SubNav";
import AutoPageHelp from "@/components/AutoPageHelp";
import KeyboardChrome from "@/components/KeyboardChrome";
import QuickRecorder from "@/components/capture/QuickRecorder";
import { KeymapProvider } from "@/components/PageKeymap";
import EntranceWelcome from "@/components/EntranceWelcome";
import { founderDisplayName } from "@/lib/founderDisplay";
import { canWrite } from "@/lib/roles";

/**
 * Shell for every signed-in Codex page. Renders the top nav (7 items),
 * then the context-sensitive sub-nav (siblings of the current page within
 * its thematic group), then the page's own content. The sub-nav renders
 * nothing on pages that have no peers (Dashboard, Upload, Publication).
 *
 * All Round-3 operational pages (Provenance, Eval, Decay, Rigor Gate,
 * Methods, Peer Review, Cascade, Post-Mortem) are consolidated under this
 * layout too — they were previously at the top level and each called
 * `getFounder()` manually, which made auth inconsistent and prevented
 * them from participating in the shared nav.
 */
export default async function AuthedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const founder = await getFounder();
  if (!founder) {
    redirect("/login");
  }

  return (
    <KeymapProvider>
      <Nav
        founder={{
          name: founderDisplayName(founder),
          username: founder.username,
          organizationSlug: founder.organization.slug,
          role: founder.role,
        }}
      />
      <SubNav />
      <AutoPageHelp />
      <KeyboardChrome />
      {/* EntranceWelcome wraps the page content so it can apply the
          `.codex-arrival` fade-in on first mount after login, and overlay
          a brief Latin welcome tag. Absent the post-login sessionStorage
          flag it's a no-op pass-through. */}
      <EntranceWelcome>{children}</EntranceWelcome>
      {/*
       * Quick-record surface — founder-only "sit, think, record"
       * capture. Render-gated on the founder's role so viewers (who
       * also pass /login but cannot write artifacts) don't see a
       * button that would 403 at /api/upload/signed/prepare anyway.
       */}
      {canWrite(founder.role) ? <QuickRecorder /> : null}
    </KeymapProvider>
  );
}
