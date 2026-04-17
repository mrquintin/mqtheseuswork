import { redirect } from "next/navigation";

import { getFounder } from "@/lib/auth";
import Gate from "@/components/Gate";

/**
 * Root of the Codex.
 *
 * The Codex is intentionally gated — there is no public marketing face.
 * An unauthenticated visitor to `/` sees the Gate (labyrinth + login);
 * an authenticated visitor is shipped straight to `/dashboard` so they
 * don't have to click through the gate on every reload.
 */
export default async function RootPage() {
  const founder = await getFounder();
  if (founder) {
    redirect("/dashboard");
  }
  return <Gate />;
}
