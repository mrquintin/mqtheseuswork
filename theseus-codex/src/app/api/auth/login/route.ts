import { NextResponse } from "next/server";
import bcrypt from "bcryptjs";
import { db } from "@/lib/db";
import { createSession } from "@/lib/auth";
import { checkLoginRateLimit, resetLoginRateLimit } from "@/lib/rateLimit";

function clientIp(req: Request): string {
  const xf = req.headers.get("x-forwarded-for");
  if (xf) return xf.split(",")[0]!.trim();
  return req.headers.get("x-real-ip") || "unknown";
}

export async function POST(req: Request) {
  try {
    const { email, password, organizationSlug } = (await req.json()) as {
      email?: string;
      password?: string;
      organizationSlug?: string;
    };
    const ip = clientIp(req);
    const rateKey = `${ip}::${(email || "").toLowerCase()}`;

    if (!email || !password) {
      return NextResponse.json({ error: "Email and password required" }, { status: 400 });
    }

    const slug =
      (organizationSlug && String(organizationSlug).trim()) ||
      process.env.DEFAULT_ORGANIZATION_SLUG ||
      "theseus-local";

    const org = await db.organization.findUnique({ where: { slug } });
    if (!org) {
      return NextResponse.json({ error: "Unknown organization" }, { status: 400 });
    }

    const founder = await db.founder.findFirst({
      where: { organizationId: org.id, email },
    });
    const valid = founder ? await bcrypt.compare(password, founder.passwordHash) : false;

    if (!founder || !valid) {
      const limited = checkLoginRateLimit(rateKey);
      if (!limited.ok) {
        return NextResponse.json(
          { error: `Too many attempts. Try again in ${limited.retryAfterSec}s.` },
          {
            status: 429,
            headers: { "Retry-After": String(limited.retryAfterSec) },
          },
        );
      }
      return NextResponse.json({ error: "Invalid credentials" }, { status: 401 });
    }

    resetLoginRateLimit(rateKey);

    await createSession(founder.id);

    await db.auditEvent.create({
      data: {
        organizationId: founder.organizationId,
        founderId: founder.id,
        action: "login",
        detail: `Logged in from web portal`,
      },
    });

    return NextResponse.json({
      id: founder.id,
      name: founder.name,
      username: founder.username,
    });
  } catch (error) {
    console.error("Login error:", error);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
