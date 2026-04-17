import { redirect } from "next/navigation";

/**
 * Legacy / bookmarked `/login` URL — preserves the path while routing every
 * sign-in through the Gate at `/`. The Gate handles both the unauthenticated
 * (show labyrinth + form) and authenticated (redirect to dashboard) paths,
 * so this file's only job is to forward the URL and keep old bookmarks
 * working after the restructure.
 *
 * The query string (e.g. `?next=/conclusions`) is preserved via the
 * middleware's `login?next=…` redirects — those land here and this file
 * forwards to `/` while keeping the search intact.
 */
export default async function LoginRedirect({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const next = typeof sp.next === "string" ? sp.next : "";
  const target = next ? `/?next=${encodeURIComponent(next)}` : "/";
  redirect(target);
}
