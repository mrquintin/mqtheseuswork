/**
 * Manual "Process now" endpoint.
 *
 * Given an `upload_id`, fires the same GitHub Actions webhook that
 * `/api/upload` fires automatically. Useful when:
 *
 *   * the auto-dispatch failed silently and the user wants to retry
 *     without waiting for the 10-minute cron;
 *   * the upload came in via API before the dispatch wiring existed
 *     (legacy rows in `queued_offline` state);
 *   * the user wants to re-run an upload in `--with-llm` mode after
 *     the naive pass already marked it `ingested`.
 *
 * Authentication follows the same pattern as the rest of the API:
 * session cookie OR `Authorization: Bearer tcx_...` API key. The
 * caller must belong to the same organization as the upload.
 */
import { NextResponse } from "next/server";
import { getFounderFromAuth } from "@/lib/apiKeyAuth";
import { db } from "@/lib/db";
import { triggerNoosphereProcessing } from "@/lib/triggerNoosphereProcessing";

export async function POST(req: Request) {
  try {
    const founder = await getFounderFromAuth(req);
    if (!founder) {
      return NextResponse.json(
        { error: "Not authenticated" },
        { status: 401 },
      );
    }

    const body = (await req.json().catch(() => ({}))) as {
      upload_id?: string;
      uploadId?: string;
      with_llm?: boolean;
      withLlm?: boolean;
    };
    const uploadId = body.upload_id || body.uploadId;
    if (!uploadId) {
      return NextResponse.json(
        { error: "upload_id is required" },
        { status: 400 },
      );
    }

    // Confirm the upload belongs to the caller's org before triggering.
    // Otherwise this would let any authed user re-run any org's
    // uploads — cheap, but it'd mess up other firms' ingest logs.
    const upload = await db.upload.findUnique({
      where: { id: uploadId },
      select: {
        id: true,
        organizationId: true,
        status: true,
        title: true,
        textContent: true,
      },
    });
    if (!upload) {
      return NextResponse.json({ error: "Upload not found" }, { status: 404 });
    }
    if (upload.organizationId !== founder.organizationId) {
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
    }

    // A bare upload with no extracted text has nothing Noosphere can do
    // with it. Signal this explicitly rather than silently queuing.
    if (!upload.textContent || upload.textContent.trim().length < 40) {
      return NextResponse.json(
        {
          error:
            "Upload has no extractable text content. Re-upload a text/PDF/DOCX " +
            "version, or set OPENAI_API_KEY so audio can be transcribed.",
        },
        { status: 422 },
      );
    }

    const withLlm = Boolean(body.with_llm ?? body.withLlm ?? true);
    const result = await triggerNoosphereProcessing(uploadId, {
      organizationId: founder.organizationId,
      withLlm,
    });

    // Annotate the upload row so the UI can show progress.
    try {
      await db.upload.update({
        where: { id: uploadId },
        data: {
          status: result.dispatched ? "processing" : upload.status,
          processLog: {
            set: [
              `— Manual re-trigger by ${founder.email} at ${new Date().toISOString()} —`,
              `— Auto-process: ${result.note} —`,
            ].join("\n"),
          },
        },
      });
    } catch {
      /* non-fatal */
    }

    await db.auditEvent
      .create({
        data: {
          organizationId: founder.organizationId,
          founderId: founder.id,
          uploadId,
          action: "trigger_processing",
          detail: `manual retrigger: dispatched=${result.dispatched} status=${result.status ?? "none"}`,
        },
      })
      .catch(() => {
        /* non-fatal */
      });

    return NextResponse.json({
      upload_id: uploadId,
      dispatched: result.dispatched,
      http_status: result.status,
      note: result.note,
      with_llm: withLlm,
    });
  } catch (error) {
    console.error("trigger-processing error:", error);
    return NextResponse.json(
      {
        error:
          `Failed to trigger processing: ${error instanceof Error ? error.message : "unknown error"}`,
      },
      { status: 500 },
    );
  }
}
