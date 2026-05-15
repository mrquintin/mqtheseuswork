import { permanentRedirect } from "next/navigation";

type Params = { id: string };

/**
 * Retired URL — public principle detail moved to `/principles/[id]`
 * in Round 21. The redirect is permanent (308) to match the index
 * redirect in `../page.tsx`, preserving the deep-link contract from
 * the old methodology surface.
 */
export default async function RetiredPublicPrincipleDetail({
  params,
}: {
  params: Promise<Params>;
}): Promise<never> {
  const { id } = await params;
  permanentRedirect(`/principles/${id}`);
}
