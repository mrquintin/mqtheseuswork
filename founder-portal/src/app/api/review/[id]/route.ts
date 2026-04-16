import { NextResponse } from "next/server";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";
import { pushReviewResolutionToNoosphere } from "@/lib/pushReviewToNoosphere";

type Verdict = "cohere" | "contradict" | "unresolved";

export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const founder = await getFounder();
  if (!founder) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { id } = await params;
  const body = (await req.json()) as {
    verdict: Verdict;
    overrule?: boolean;
    note?: string;
  };

  if (!body.verdict || !["cohere", "contradict", "unresolved"].includes(body.verdict)) {
    return NextResponse.json({ error: "Invalid verdict" }, { status: 400 });
  }

  const item = await db.reviewItem.findUnique({ where: { id } });
  if (!item) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  await db.reviewItem.update({
    where: { id },
    data: {
      status: "done",
      humanVerdict: body.verdict,
      humanOverrule: Boolean(body.overrule),
      resolutionNote: body.note || "",
      resolvedAt: new Date(),
      resolvedByFounderId: founder.id,
    },
  });

  if (item.noosphereId) {
    const py = await pushReviewResolutionToNoosphere({
      reviewId: item.noosphereId,
      verdict: body.verdict,
      overrule: Boolean(body.overrule),
      aggregatorVerdict: item.aggregatorVerdict,
      founderId: founder.noosphereId || founder.id,
      note: body.note || "",
    });

    if (!py.ok) {
      return NextResponse.json(
        { ok: true, warning: "Portal updated; Noosphere sync failed", detail: py.stderr },
        { status: 200 },
      );
    }
  }

  return NextResponse.json({ ok: true });
}
