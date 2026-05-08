/**
 * Minimal type declaration for `js-yaml`. The package ships no
 * top-level types, and we only need `load` for parsing the curated
 * `<method>.FAILURES.yaml` catalogs at request time. Adding the full
 * upstream `@types/js-yaml` would pull in transitive declarations we
 * don't otherwise use.
 */
declare module "js-yaml" {
  export function load(input: string): unknown;
  const _default: { load: typeof load };
  export default _default;
}
