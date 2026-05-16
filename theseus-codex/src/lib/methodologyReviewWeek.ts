import type { AttentionItem } from "@/lib/attention";
import type { AttentionQueueId } from "@/lib/attentionShared";
import type { TenantContext } from "@/lib/tenant";

/**
 * Web-side helper for the firm's quarterly Methodology Review Week.
 *
 * The schedule, day focus, and queue-per-day filter live in the Python
 * module `noosphere.inquiry.methodology_review_week`; this file mirrors
 * the same vocabulary onto the web app so the founder can triage from
 * the unified attention queue and persist day summaries to Prisma.
 *
 * The shared rules pinned here (and mirrored in the Python module's
 * tests):
 *
 *   - Five working days, Monday → Friday.
 *   - Day-by-day focus is fixed: drift, failure modes, domain bounds,
 *     retirement candidates, methodology section.
 *   - Opt-in per founder. Postponement and skipping are recorded, not
 *     punished. The public methodology page surfaces the last completed
 *     week and the next scheduled week from these rows.
 */

export const DAY_FOCUSES = [
  "drift_events",
  "failure_modes",
  "domain_bounds",
  "retirement_candidates",
  "methodology_section",
] as const;

export type DayFocus = (typeof DAY_FOCUSES)[number];

export const DAY_LABELS: Record<DayFocus, string> = {
  drift_events: "Drift events review",
  failure_modes: "Failure-mode catalog review",
  domain_bounds: "Domain-bound review",
  retirement_candidates: "Retirement candidate review",
  methodology_section: "Methodology section writeup",
};

export const QUEUES_BY_FOCUS: Record<DayFocus, ReadonlySet<AttentionQueueId>> = {
  drift_events: new Set<AttentionQueueId>(["drift", "calibration_breach"]),
  failure_modes: new Set<AttentionQueueId>(["peer_review", "citation_verdict"]),
  domain_bounds: new Set<AttentionQueueId>([
    "source_triage",
    "retraction_propagation",
  ]),
  retirement_candidates: new Set<AttentionQueueId>([
    "calibration_breach",
    "drift",
  ]),
  methodology_section: new Set<AttentionQueueId>(),
};

export const REVIEW_WEEK_STATUSES = [
  "scheduled",
  "active",
  "completed",
  "postponed",
  "skipped",
] as const;

export type ReviewWeekStatus = (typeof REVIEW_WEEK_STATUSES)[number];

export const DRAFT_BANNER =
  "**DRAFT — generated from the day's queue; the founder writes the final.**";

async function loadDb() {
  const { db } = await import("@/lib/db");
  return db;
}

// ── Schedule generation (mirrors the Python module) ───────────────────

export type ReviewDay = {
  dayIndex: number;
  focus: DayFocus;
  on: Date;
  label: string;
};

export type ReviewWeek = {
  year: number;
  quarter: number;
  slug: string;
  label: string;
  status: ReviewWeekStatus;
  startDate: Date;
  endDate: Date;
  postponedTo: Date | null;
  postponeReason: string;
  days: ReviewDay[];
};

function firstMondayOnOrAfter(d: Date): Date {
  const day = d.getUTCDay(); // 0 = Sunday, 1 = Monday, …
  const mondayOffset = day === 0 ? 1 : day === 1 ? 0 : 8 - day;
  const out = new Date(
    Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + mondayOffset),
  );
  return out;
}

export function defaultStartForQuarter(year: number, quarter: number): Date {
  if (quarter < 1 || quarter > 4) {
    throw new Error(`quarter must be 1..4, got ${quarter}`);
  }
  const monthIdx = (quarter - 1) * 3 + 1; // 1, 4, 7, 10 (0-indexed)
  return firstMondayOnOrAfter(new Date(Date.UTC(year, monthIdx, 1)));
}

function quarterSlug(year: number, quarter: number): string {
  return `${year}_Q${quarter}_MethodologyReviewWeek`;
}

function addUtcDays(d: Date, days: number): Date {
  return new Date(
    Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + days),
  );
}

function buildDays(start: Date): ReviewDay[] {
  if (start.getUTCDay() !== 1) {
    throw new Error("Methodology Review Week must start on a Monday");
  }
  return DAY_FOCUSES.map((focus, i) => ({
    dayIndex: i + 1,
    focus,
    on: addUtcDays(start, i),
    label: DAY_LABELS[focus],
  }));
}

/**
 * Build a default-scheduled week from (year, quarter). The DB row, if
 * any, supersedes this — call `getReviewWeek` to fetch the live row.
 */
export function scheduleForQuarter(year: number, quarter: number): ReviewWeek {
  const start = defaultStartForQuarter(year, quarter);
  const days = buildDays(start);
  return {
    year,
    quarter,
    slug: quarterSlug(year, quarter),
    label: `${year} Q${quarter} Methodology Review Week`,
    status: "scheduled",
    startDate: start,
    endDate: days[days.length - 1].on,
    postponedTo: null,
    postponeReason: "",
    days,
  };
}

function quarterOf(d: Date): number {
  return Math.floor(d.getUTCMonth() / 3) + 1;
}

/** Next review week whose start is on or after `today`. */
export function nextReviewWeekAfter(today: Date): ReviewWeek {
  const startYear = today.getUTCFullYear();
  for (let yearOffset = 0; yearOffset <= 2; yearOffset++) {
    const year = startYear + yearOffset;
    for (const quarter of [1, 2, 3, 4]) {
      const week = scheduleForQuarter(year, quarter);
      if (week.startDate.getTime() >= today.getTime()) {
        return week;
      }
    }
  }
  throw new Error("no scheduled review week within 2-year horizon");
}

// ── Persistence (Prisma) ──────────────────────────────────────────────

type ReviewWeekRowCore = {
  year: number;
  quarter: number;
  startDate: Date;
  endDate: Date;
  status: string;
  postponedTo: Date | null;
  postponeReason: string;
};

async function loadOrSeedWeekRow(
  tenant: TenantContext,
  year: number,
  quarter: number,
) {
  const db = await loadDb();
  const existing = await db.methodologyReviewWeek.findUnique({
    where: {
      organizationId_year_quarter: {
        organizationId: tenant.organizationId,
        year,
        quarter,
      },
    },
  });
  if (existing) return existing;
  const scheduled = scheduleForQuarter(year, quarter);
  return db.methodologyReviewWeek.create({
    data: {
      organizationId: tenant.organizationId,
      year,
      quarter,
      startDate: scheduled.startDate,
      endDate: scheduled.endDate,
      status: "scheduled",
    },
  });
}

function rowToWeek(row: ReviewWeekRowCore): ReviewWeek {
  const start = new Date(row.startDate);
  // Re-derive days from the live start date so a postponed row's days
  // shift with it.
  const monday = firstMondayOnOrAfter(start);
  const days = buildDays(monday);
  return {
    year: row.year,
    quarter: row.quarter,
    slug: quarterSlug(row.year, row.quarter),
    label: `${row.year} Q${row.quarter} Methodology Review Week`,
    status: (REVIEW_WEEK_STATUSES as readonly string[]).includes(row.status)
      ? (row.status as ReviewWeekStatus)
      : "scheduled",
    startDate: start,
    endDate: new Date(row.endDate),
    postponedTo: row.postponedTo ? new Date(row.postponedTo) : null,
    postponeReason: row.postponeReason ?? "",
    days,
  };
}

/**
 * Return the review week the founder is currently inside, if any.
 * A week is "active" when today is between its startDate and endDate
 * (inclusive) AND its status is not `skipped`.
 */
export async function getActiveReviewWeek(
  tenant: TenantContext,
  now: Date = new Date(),
): Promise<ReviewWeek | null> {
  const db = await loadDb();
  const candidates = await db.methodologyReviewWeek.findMany({
    where: {
      organizationId: tenant.organizationId,
      status: { in: ["scheduled", "active"] },
      startDate: { lte: now },
      endDate: { gte: now },
    },
    orderBy: { startDate: "desc" },
    take: 1,
  });
  if (candidates.length === 0) return null;
  return rowToWeek(candidates[0]);
}

export async function getOrSeedWeek(
  tenant: TenantContext,
  year: number,
  quarter: number,
): Promise<ReviewWeek> {
  const row = await loadOrSeedWeekRow(tenant, year, quarter);
  return rowToWeek(row);
}

/**
 * Fetch the current-or-next review week for the hub page. Prefers an
 * active week; falls back to the soonest scheduled week; finally
 * synthesizes the schedule from the calendar if no row exists yet.
 */
export async function getCurrentOrNextWeek(
  tenant: TenantContext,
  now: Date = new Date(),
): Promise<ReviewWeek> {
  const active = await getActiveReviewWeek(tenant, now);
  if (active) return active;
  const db = await loadDb();
  const upcoming = await db.methodologyReviewWeek.findFirst({
    where: {
      organizationId: tenant.organizationId,
      status: { in: ["scheduled", "postponed"] },
      startDate: { gte: now },
    },
    orderBy: { startDate: "asc" },
  });
  if (upcoming) return rowToWeek(upcoming);
  const fallback = nextReviewWeekAfter(now);
  return getOrSeedWeek(tenant, fallback.year, fallback.quarter);
}

// ── Day-page data ─────────────────────────────────────────────────────

export type DaySummaryRow = {
  id: string;
  weekId: string;
  dayIndex: number;
  focus: DayFocus;
  draftBody: string;
  draftGeneratedAt: Date | null;
  body: string;
  editCount: number;
  signature: string;
  signedAt: Date | null;
  signingKeyFingerprint: string;
  createdAt: Date;
  updatedAt: Date;
};

export type DayPageData = {
  week: ReviewWeek;
  day: ReviewDay;
  summary: DaySummaryRow | null;
  /** Items in the unified attention queue filtered to this day's focus. */
  queue: AttentionItem[];
};

export function filterAttentionForDay(
  items: AttentionItem[],
  focus: DayFocus,
): AttentionItem[] {
  const allowed = QUEUES_BY_FOCUS[focus];
  if (allowed.size === 0) return [];
  return items.filter((item) => allowed.has(item.queue));
}

export async function loadDayPage(
  tenant: TenantContext,
  year: number,
  quarter: number,
  dayIndex: number,
): Promise<DayPageData> {
  if (dayIndex < 1 || dayIndex > DAY_FOCUSES.length) {
    throw new Error(`dayIndex must be 1..${DAY_FOCUSES.length}, got ${dayIndex}`);
  }
  const week = await getOrSeedWeek(tenant, year, quarter);
  const day = week.days[dayIndex - 1];
  const { gatherAttentionItems } = await import("@/lib/attention");
  const [summary, queue] = await Promise.all([
    loadDaySummary(tenant, week, dayIndex),
    gatherAttentionItems(tenant).catch((err) => {
      console.error("[methodology-review-week] queue fetch failed:", err);
      return [] as AttentionItem[];
    }),
  ]);
  return {
    week,
    day,
    summary,
    queue: filterAttentionForDay(queue, day.focus),
  };
}

async function loadDaySummary(
  tenant: TenantContext,
  week: ReviewWeek,
  dayIndex: number,
): Promise<DaySummaryRow | null> {
  const db = await loadDb();
  const weekRow = await db.methodologyReviewWeek.findUnique({
    where: {
      organizationId_year_quarter: {
        organizationId: tenant.organizationId,
        year: week.year,
        quarter: week.quarter,
      },
    },
  });
  if (!weekRow) return null;
  const row = await db.methodologyReviewDaySummary.findUnique({
    where: { weekId_dayIndex: { weekId: weekRow.id, dayIndex } },
  });
  if (!row) return null;
  return {
    id: row.id,
    weekId: row.weekId,
    dayIndex: row.dayIndex,
    focus: row.focus as DayFocus,
    draftBody: row.draftBody,
    draftGeneratedAt: row.draftGeneratedAt,
    body: row.body,
    editCount: row.editCount,
    signature: row.signature,
    signedAt: row.signedAt,
    signingKeyFingerprint: row.signingKeyFingerprint,
    createdAt: row.createdAt,
    updatedAt: row.updatedAt,
  };
}

// ── Draft generation ──────────────────────────────────────────────────

/**
 * Generate a clearly-labelled draft summary from the day's filtered
 * queue. The draft begins with the DRAFT banner and lists queue items
 * with their severity. The founder reads it, then writes their own
 * final — the draft is never auto-saved to the body column.
 */
export function draftDaySummaryFromQueue(
  week: ReviewWeek,
  dayIndex: number,
  queueItems: AttentionItem[],
): string {
  if (dayIndex < 1 || dayIndex > DAY_FOCUSES.length) {
    throw new Error(`dayIndex must be 1..${DAY_FOCUSES.length}, got ${dayIndex}`);
  }
  const focus = DAY_FOCUSES[dayIndex - 1];
  const filtered = filterAttentionForDay(queueItems, focus);
  const counts = { high: 0, medium: 0, low: 0 } as Record<string, number>;
  for (const it of filtered) {
    counts[it.severity] = (counts[it.severity] ?? 0) + 1;
  }
  const lines: string[] = [DRAFT_BANNER, ""];
  lines.push(`# ${DAY_LABELS[focus]} — ${week.label} (Day ${dayIndex})`);
  lines.push("");
  if (focus === "methodology_section") {
    lines.push(
      "Day 5 is the writeup pass. The agent does not draft prose for " +
        "the seasonal review's methodology section; the founder writes " +
        "it from the four days of triage notes above.",
    );
    lines.push("");
  } else {
    lines.push(
      `${filtered.length} item(s) in the day's queue — ${counts.high} high, ${counts.medium} medium, ${counts.low} low.`,
    );
    lines.push("");
    if (filtered.length === 0) {
      lines.push(
        "The queue is empty for this focus today. Record the absence.",
      );
    } else {
      lines.push("## Items");
      lines.push("");
      for (const it of filtered.slice(0, 20)) {
        const preview = it.preview.replace(/\s+/g, " ").trim();
        lines.push(
          `- [${it.severity}] ${it.queue}/${it.itemId} — ${preview}`,
        );
      }
      if (filtered.length > 20) {
        lines.push(
          `- … plus ${filtered.length - 20} more (see the queue page).`,
        );
      }
    }
    lines.push("");
  }
  return lines.join("\n").trimEnd() + "\n";
}

// ── History + public hint ─────────────────────────────────────────────

export type HistoricalReviewWeek = {
  week: ReviewWeek;
  daysWithSummary: number;
  daysSigned: number;
};

export async function listHistoricalReviewWeeks(
  tenant: TenantContext,
  options: { now?: Date; limit?: number } = {},
): Promise<HistoricalReviewWeek[]> {
  const now = options.now ?? new Date();
  const db = await loadDb();
  const rows = await db.methodologyReviewWeek.findMany({
    where: {
      organizationId: tenant.organizationId,
      endDate: { lt: now },
    },
    orderBy: { startDate: "desc" },
    take: options.limit ?? 50,
    include: { daySummaries: true },
  });
  return rows.map((row) => ({
    week: rowToWeek(row),
    daysWithSummary: row.daySummaries.filter((s) => s.body.trim().length > 0)
      .length,
    daysSigned: row.daySummaries.filter(
      (s) => s.signature.length > 0 && s.signedAt !== null,
    ).length,
  }));
}

export type PublicHint = {
  lastOn: Date | null;
  nextOn: Date | null;
  text: string;
};

function formatHintDate(d: Date | null): string {
  if (!d) return "—";
  return d.toISOString().slice(0, 10);
}

/**
 * Build the line the public methodology page surfaces:
 *
 *     Last review week: <date>; next review week: <date>
 *
 * The "last" date is the end-of-week of the most recent COMPLETED week
 * (skipped weeks are not "last"). The "next" date is the start of the
 * soonest scheduled or postponed week on or after today; if no DB row
 * exists, fall back to the calendar default.
 *
 * The public site is single-firm, so this query is not filtered by
 * organization id — the firm is whatever organization has rows. Pass
 * `organizationId` to restrict to a specific tenant when calling from
 * a multi-tenant context.
 */
export async function publicReviewWeekHint(
  options: { organizationId?: string; now?: Date } = {},
): Promise<PublicHint> {
  const now = options.now ?? new Date();
  const orgScope = options.organizationId
    ? { organizationId: options.organizationId }
    : {};
  let lastOn: Date | null = null;
  let nextOn: Date | null = null;
  try {
    const db = await loadDb();
    const lastCompleted = await db.methodologyReviewWeek.findFirst({
      where: {
        ...orgScope,
        status: "completed",
        endDate: { lt: now },
      },
      orderBy: { endDate: "desc" },
    });
    if (lastCompleted) {
      lastOn = lastCompleted.endDate;
    }
    const upcoming = await db.methodologyReviewWeek.findFirst({
      where: {
        ...orgScope,
        status: { in: ["scheduled", "postponed"] },
        startDate: { gte: now },
      },
      orderBy: { startDate: "asc" },
    });
    if (upcoming) {
      nextOn = upcoming.startDate;
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    if (!message.includes("DATABASE_URL must be set")) {
      console.error("[methodology-review-week] public hint query failed:", err);
    }
  }
  if (!nextOn) {
    try {
      nextOn = nextReviewWeekAfter(now).startDate;
    } catch {
      nextOn = null;
    }
  }
  return {
    lastOn,
    nextOn,
    text: `Last review week: ${formatHintDate(lastOn)}; next review week: ${formatHintDate(nextOn)}`,
  };
}
