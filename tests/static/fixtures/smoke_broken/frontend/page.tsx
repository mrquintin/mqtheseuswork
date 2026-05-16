// Deliberately broken page: imports a module that does not exist.
// The smoke harness's frontend_routes._static_check should flag the
// unresolved import. This fixture is referenced by
// tests/static/test_smoke_harness_itself.py — do not "fix" the import.
import { something } from "./this-module-does-not-exist";

export default function BrokenPage() {
  return <main>{String(something)}</main>;
}
