"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { db } from "@/lib/db";
import { requireTenantContext } from "@/lib/tenant";

function sourceFromUrl(url: URL): "POLYMARKET" | "KALSHI" | null {
  const host = url.hostname.toLowerCase();
  if (host.endsWith("polymarket.com")) return "POLYMARKET";
  if (host.endsWith("kalshi.com")) return "KALSHI";
  return null;
}

function externalIdFromUrl(url: URL): string | null {
  const parts = url.pathname.split("/").map((part) => part.trim()).filter(Boolean);
  return parts.at(-1) ?? null;
}

export async function addWatchedMarket(formData: FormData) {
  const tenant = await requireTenantContext();
  if (!tenant) redirect("/login");

  const raw = String(formData.get("marketUrl") ?? "").trim();
  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    redirect("/forecasts/portfolio?watch=invalid");
  }

  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
    redirect("/forecasts/portfolio?watch=invalid");
  }

  const source = sourceFromUrl(parsed);
  if (!source) {
    redirect("/forecasts/portfolio?watch=unsupported");
  }

  await db.watchedMarket.upsert({
    where: {
      organizationId_url: {
        organizationId: tenant.organizationId,
        url: parsed.toString(),
      },
    },
    update: {
      externalId: externalIdFromUrl(parsed),
      source,
      status: "ACTIVE",
    },
    create: {
      externalId: externalIdFromUrl(parsed),
      organizationId: tenant.organizationId,
      source,
      status: "ACTIVE",
      url: parsed.toString(),
    },
  });

  revalidatePath("/forecasts/portfolio");
  redirect("/forecasts/portfolio?watch=added");
}
