import { redirect } from "next/navigation";

import { getFounder } from "@/lib/auth";
import Gate from "@/components/Gate";

/**
 * Founder login.
 *
 * The Codex now has two surfaces: a public blog at `/` and the private
 * founder workspace at `/dashboard` (and every other `(authed)/*`
 * route). This file hosts the Gate — the amber-oracle labyrinth + form
 * component — which was previously at `/`. Moving it here frees the
 * root for the blog index without losing the cinematic sign-in ritual
 * (Armillary Ignition animation on success still runs).
 *
 * Flow:
 *   - Unauthenticated: render Gate.
 *   - Authenticated:   redirect to `?next=…` if provided (so a user
 *                      who hit a protected page while signed out
 *                      lands where they meant to go), otherwise to
 *                      `/dashboard`.
 */
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const next = typeof sp.next === "string" ? sp.next : "";
  const founder = await getFounder();
  if (founder) {
    redirect(next || "/dashboard");
  }
  return <Gate />;
}
