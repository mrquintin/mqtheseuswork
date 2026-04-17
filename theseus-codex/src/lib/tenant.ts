import { getFounder } from "@/lib/auth";

/** Request-scoped tenant identity (every authenticated portal request). */
export type TenantContext = {
  organizationId: string;
  organizationSlug: string;
  founderId: string;
  role: string;
};

export async function requireTenantContext(): Promise<TenantContext | null> {
  const founder = await getFounder();
  if (!founder) return null;
  const slug = founder.organization?.slug ?? "";
  if (!slug) {
    throw new Error("Founder missing organization relation");
  }
  return {
    organizationId: founder.organizationId,
    organizationSlug: slug,
    founderId: founder.id,
    role: founder.role,
  };
}
