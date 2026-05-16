// Fixture for the "page lost its default export" regression. A real
// page.tsx that ships without a default export still type-checks (the
// file is valid TS) but the route 500s at SSR time.
export function NamedOnly() {
  return null;
}
