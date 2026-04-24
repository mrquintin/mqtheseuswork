import LibraryBrowser from "./LibraryBrowser";
import { requireTenantContext } from "@/lib/tenant";

/**
 * /library — org-wide upload inventory.
 *
 * The Codex is collective. Every founder can see what's in the library
 * and who put it there. Only owners can delete their own entries; peers
 * can open a "please delete" request that the owner reviews.
 *
 * The server component here does only the auth check — all data
 * fetching is in the client component so we can reload after every
 * mutation (accept / decline / delete / request / cancel) without a
 * full page navigation.
 */
export default async function LibraryPage() {
  const tenant = await requireTenantContext();
  if (!tenant) return null;

  return (
    <main
      style={{
        maxWidth: "1000px",
        margin: "0 auto",
        padding: "2rem 2rem 4rem",
      }}
    >
      <header style={{ marginBottom: "1.75rem" }}>
        <h1
          style={{
            fontFamily: "'Cinzel Decorative', 'Cinzel', serif",
            fontSize: "2rem",
            letterSpacing: "0.18em",
            color: "var(--amber)",
            textShadow: "var(--glow-md)",
            margin: 0,
          }}
        >
          Bibliotheca
        </h1>
        <p
          className="mono"
          style={{
            fontSize: "0.62rem",
            letterSpacing: "0.28em",
            textTransform: "uppercase",
            color: "var(--amber-dim)",
            marginTop: "0.25rem",
            marginBottom: 0,
          }}
        >
          Library · Every upload in the firm
        </p>
        <p
          style={{
            fontFamily: "'EB Garamond', serif",
            fontStyle: "italic",
            fontSize: "1.05rem",
            color: "var(--parchment-dim)",
            marginTop: "0.6rem",
            marginBottom: 0,
            lineHeight: 1.55,
            maxWidth: "44em",
          }}
        >
          Who contributed what. Owners can delete their own entries
          directly. For material you didn&rsquo;t upload, send a deletion
          request — the owner decides. Every action leaves an audit
          trail.
        </p>
      </header>

      <LibraryBrowser />
    </main>
  );
}
