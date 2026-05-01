import { getFounder } from "@/lib/auth";
import { founderDisplayName } from "@/lib/founderDisplay";

/** Request-scoped tenant identity (every authenticated portal request). */
export type TenantContext = {
  organizationId: string;
  organizationSlug: string;
  founderId: string;
  founderName: string;
  founderUsername: string;
  founderDisplayName?: string | null;
  accountNudgeDismissedAt?: Date | null;
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
    founderName: founderDisplayName(founder),
    founderUsername: founder.username,
    founderDisplayName: founder.displayName,
    accountNudgeDismissedAt: founder.accountNudgeDismissedAt,
    role: founder.role,
  };
}
