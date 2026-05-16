/**
 * `manual.operator.entered` predicate — kept in its own module so
 * client components can import it without pulling in the Prisma /
 * `pg` chain that lives behind `algorithmsPublicApi`.
 *
 * Anything `manual.*` is treated as operator-entered: the value is
 * real, but readers should know it is hand-curated rather than
 * ingested.
 */

export type ObservabilitySource = string;

export function isOperatorEntered(
  input: { observability_source: ObservabilitySource } | ObservabilitySource,
): boolean {
  const source =
    typeof input === "string" ? input : input.observability_source;
  return source === "manual.operator.entered" || source.startsWith("manual.");
}
