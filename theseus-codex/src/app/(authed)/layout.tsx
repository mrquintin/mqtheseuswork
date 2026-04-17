import { redirect } from "next/navigation";
import { getFounder } from "@/lib/auth";
import Nav from "@/components/Nav";
import SubNav from "@/components/SubNav";
import AutoPageHelp from "@/components/AutoPageHelp";
import NavTransition from "@/components/NavTransition";

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
    <>
      <Nav
        founder={{
          name: founder.name,
          username: founder.username,
          organizationSlug: founder.organization.slug,
        }}
      />
      <SubNav />
      <AutoPageHelp />
      {children}
      <NavTransition />
    </>
  );
}
