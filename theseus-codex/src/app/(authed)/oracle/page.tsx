import OracleClient from "./OracleClient";
import { requireTenantContext } from "@/lib/tenant";

/**
 * /oracle — founder-facing synthesis surface (prompt 09).
 *
 * The Oracle is the query layer: a founder asks a question, the
 * synthesizer pulls relevant material from the corpus and composes an
 * answer. Prompt 09 adds the ProvenanceFilter — four checkboxes that
 * tell the synthesizer which buckets to pull from (proprietary by
 * default; endorsed by default; studied / opposing opt-in only).
 *
 * The server component does only the auth gate; the actual filter +
 * query lives in the client so the founder can twiddle checkboxes and
 * see counts without a round trip.
 */
export default async function OraclePage() {
  const tenant = await requireTenantContext();
  if (!tenant) return null;
  return <OracleClient />;
}
