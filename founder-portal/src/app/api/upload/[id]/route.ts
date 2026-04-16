import { NextResponse } from "next/server";
import { getFounder } from "@/lib/auth";
import { db } from "@/lib/db";

/**
 * GET /api/upload/:id — poll status and streamed process log.
 */
export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const founder = await getFounder();
  if (!founder) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const { id } = await params;

  const upload = await db.upload.findFirst({
    where: { id, organizationId: founder.organizationId },
    select: {
      id: true,
      founderId: true,
      organizationId: true,
      title: true,
      status: true,
      processLog: true,
      claimsCount: true,
      methodCount: true,
      substCount: true,
      principleCount: true,
      errorMessage: true,
      createdAt: true,
      updatedAt: true,
    },
  });

  if (!upload) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const sameOrg = upload.organizationId === founder.organizationId;
  if (!sameOrg) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }
  if (upload.founderId !== founder.id && founder.role !== "admin") {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  return NextResponse.json(upload);
}
