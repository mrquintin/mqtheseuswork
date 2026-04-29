function cleanUrl(raw: string | undefined): string | null {
  const value = raw?.trim();
  if (!value) return null;
  return value.replace(/\/+$/, "");
}

export function getPublicSiteUrl(): string {
  const explicit =
    cleanUrl(process.env.THESEUS_PUBLIC_SITE_URL) ||
    cleanUrl(process.env.NEXT_PUBLIC_SITE_URL);
  if (explicit) return explicit;

  const vercelHost =
    cleanUrl(process.env.VERCEL_PROJECT_PRODUCTION_URL) ||
    cleanUrl(process.env.VERCEL_URL);
  if (vercelHost) {
    return vercelHost.startsWith("http") ? vercelHost : `https://${vercelHost}`;
  }

  if (process.env.NODE_ENV === "production") {
    return "https://theseuscodex.com";
  }

  return "http://localhost:3000";
}

export const SITE = getPublicSiteUrl();
