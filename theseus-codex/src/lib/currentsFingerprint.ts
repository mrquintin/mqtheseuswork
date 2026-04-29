import { createHash } from "crypto";

function cleanForwardedValue(value: string): string {
  return value.trim().replace(/^"|"$/g, "").replace(/^\[|\]$/g, "");
}

export function clientIpFor(req: Request): string {
  const forwardedFor = req.headers.get("x-forwarded-for");
  if (forwardedFor) {
    const first = forwardedFor.split(",", 1)[0]?.trim();
    if (first) return first;
  }

  const forwarded = req.headers.get("forwarded");
  if (forwarded) {
    for (const entry of forwarded.split(",")) {
      for (const part of entry.split(";")) {
        const [rawKey, ...rest] = part.split("=");
        if (rawKey?.trim().toLowerCase() !== "for" || rest.length === 0) continue;
        const value = cleanForwardedValue(rest.join("="));
        if (value) return value;
      }
    }
  }

  const maybeIp = (req as Request & { ip?: string }).ip;
  return maybeIp?.trim() || "unknown";
}

export function utcDay(date = new Date()): string {
  return date.toISOString().slice(0, 10);
}

export function fingerprintFor(req: Request, date = new Date()): string {
  const ip = clientIpFor(req);
  const userAgent = req.headers.get("user-agent") ?? "";
  const material = `${ip}\n${userAgent}\n${utcDay(date)}`;
  return createHash("sha256").update(material, "utf8").digest("hex").slice(0, 32);
}
