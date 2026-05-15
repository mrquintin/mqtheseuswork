"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { useHotkey } from "@/lib/hotkeys";
import {
  AudioRecorder,
  MAX_RECORDING_MS,
  type RecorderState,
  type RecordingResult,
} from "@/lib/audio-recorder";
import RecordingPulse from "./RecordingPulse";

/**
 * Founder-only "sit, think, record" quick capture surface.
 *
 * Mounted in (authed)/layout.tsx so it shows on every authed page. The
 * collapsed surface is a small floating button anchored to the bottom-
 * right corner of the viewport; clicking it (or pressing Cmd+Shift+R)
 * opens an in-page recorder with pause/resume/save/discard. The pulse
 * dot inside the button itself stays visible whenever a recording is
 * underway, even with the panel collapsed, so the founder can never
 * forget the mic is hot.
 *
 * Uploads ride the existing /api/upload/signed/{prepare,finalize} path
 * the same way the upload page does — voice memos are just another
 * artifact, tagged with `sourceType=voice_memo` so the captures queue
 * and the principle extractor can recognise them.
 */
export default function QuickRecorder() {
  const router = useRouter();
  const recorderRef = useRef<AudioRecorder | null>(null);
  const [state, setState] = useState<RecorderState>("idle");
  const [elapsedMs, setElapsedMs] = useState(0);
  const [panelOpen, setPanelOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [lastSavedId, setLastSavedId] = useState<string | null>(null);

  // Build (or reset) the recorder on first interaction. We do NOT
  // construct it on mount — that would request mic permission on
  // every page navigation. The recorder also self-tears-down to idle
  // after each save/discard.
  const ensureRecorder = useCallback((): AudioRecorder => {
    if (recorderRef.current) return recorderRef.current;
    const inst = new AudioRecorder({
      onStateChange: (next) => setState(next),
      onTick: (ms) => setElapsedMs(ms),
      onCeilingReached: () => {
        setErrorMessage(
          "30-minute ceiling reached — recording auto-stopped. " +
            "Save what you have, then open a new capture for the rest.",
        );
      },
      onError: (err) => {
        setErrorMessage(err.message);
        setUploading(false);
      },
    });
    recorderRef.current = inst;
    return inst;
  }, []);

  const openPanel = useCallback(() => {
    setPanelOpen(true);
    setErrorMessage(null);
    setLastSavedId(null);
  }, []);

  const startRecording = useCallback(async () => {
    setErrorMessage(null);
    setLastSavedId(null);
    setPanelOpen(true);
    const rec = ensureRecorder();
    try {
      await rec.start();
    } catch {
      /* error already surfaced via onError */
    }
  }, [ensureRecorder]);

  const toggleFromHotkey = useCallback(() => {
    const rec = recorderRef.current;
    if (!rec || rec.getState() === "idle") {
      void startRecording();
      return;
    }
    if (rec.getState() === "recording") {
      rec.pause();
    } else if (rec.getState() === "paused") {
      rec.resume();
    }
  }, [startRecording]);

  useHotkey("mod+shift+r", toggleFromHotkey, { allowInEditable: true });

  const handlePauseResume = useCallback(() => {
    const rec = recorderRef.current;
    if (!rec) return;
    if (rec.getState() === "recording") rec.pause();
    else if (rec.getState() === "paused") rec.resume();
  }, []);

  const handleDiscard = useCallback(() => {
    const rec = recorderRef.current;
    if (!rec) {
      setPanelOpen(false);
      return;
    }
    if (rec.getState() !== "idle") {
      const confirmed = window.confirm(
        "Discard this recording? The audio is still in your browser and will be gone after you confirm.",
      );
      if (!confirmed) return;
      rec.discard();
    }
    recorderRef.current = null;
    setElapsedMs(0);
    setPanelOpen(false);
  }, []);

  const handleSave = useCallback(async () => {
    const rec = recorderRef.current;
    if (!rec) return;
    if (rec.getState() === "recording" || rec.getState() === "paused") {
      try {
        setUploading(true);
        const result = await rec.stop();
        const uploadId = await uploadVoiceMemo(result);
        recorderRef.current = null;
        setElapsedMs(0);
        setLastSavedId(uploadId);
        setUploading(false);
        // Refresh server components so the dashboard's latest-capture
        // card and the captures queue both pick up the new row without
        // a full reload.
        router.refresh();
      } catch (err) {
        setUploading(false);
        setErrorMessage(err instanceof Error ? err.message : String(err));
      }
    }
  }, [router]);

  // Clean up the active mic stream on unmount (route change, sign-out).
  useEffect(
    () => () => {
      recorderRef.current?.discard();
      recorderRef.current = null;
    },
    [],
  );

  const isActive = state === "recording" || state === "paused";

  return (
    <div
      data-testid="quick-recorder-root"
      style={{
        position: "fixed",
        right: "1.25rem",
        bottom: "1.25rem",
        zIndex: 9999,
        fontFamily: "inherit",
      }}
    >
      {panelOpen ? (
        <RecorderPanel
          state={state}
          elapsedMs={elapsedMs}
          uploading={uploading}
          errorMessage={errorMessage}
          lastSavedId={lastSavedId}
          onStart={startRecording}
          onPauseResume={handlePauseResume}
          onSave={handleSave}
          onDiscard={handleDiscard}
          onDismiss={() => setPanelOpen(false)}
        />
      ) : (
        <button
          type="button"
          aria-label={
            isActive
              ? "Open quick recorder (recording in progress)"
              : "Open quick recorder (Cmd+Shift+R)"
          }
          onClick={openPanel}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.5rem",
            padding: "0.55rem 0.85rem",
            borderRadius: 999,
            border: "1px solid rgba(0,0,0,0.12)",
            background: isActive ? "#fff1ec" : "#fff",
            color: "#1f1f1f",
            boxShadow:
              "0 6px 18px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.08)",
            cursor: "pointer",
            fontSize: "0.85rem",
            fontWeight: 500,
          }}
        >
          {isActive ? (
            <RecordingPulse
              state={state === "paused" ? "paused" : "recording"}
              elapsedMs={elapsedMs}
              compact
            />
          ) : (
            <>
              <span
                aria-hidden="true"
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: "#d62828",
                  display: "inline-block",
                }}
              />
              <span>Quick record</span>
            </>
          )}
        </button>
      )}
    </div>
  );
}

interface RecorderPanelProps {
  state: RecorderState;
  elapsedMs: number;
  uploading: boolean;
  errorMessage: string | null;
  lastSavedId: string | null;
  onStart: () => void;
  onPauseResume: () => void;
  onSave: () => void;
  onDiscard: () => void;
  onDismiss: () => void;
}

function RecorderPanel({
  state,
  elapsedMs,
  uploading,
  errorMessage,
  lastSavedId,
  onStart,
  onPauseResume,
  onSave,
  onDiscard,
  onDismiss,
}: RecorderPanelProps) {
  const canStart = state === "idle";
  const canPauseResume = state === "recording" || state === "paused";
  const canSave = (state === "recording" || state === "paused") && !uploading;
  const ceilingPct = Math.min(100, (elapsedMs / MAX_RECORDING_MS) * 100);
  return (
    <div
      role="dialog"
      aria-label="Quick recorder"
      data-testid="quick-recorder-panel"
      style={{
        width: "min(360px, calc(100vw - 2rem))",
        background: "#fff",
        border: "1px solid rgba(0,0,0,0.12)",
        borderRadius: 12,
        padding: "0.95rem 1rem 1rem",
        boxShadow:
          "0 12px 30px rgba(0,0,0,0.18), 0 2px 4px rgba(0,0,0,0.08)",
        color: "#1f1f1f",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          marginBottom: "0.5rem",
        }}
      >
        <strong style={{ fontSize: "0.95rem" }}>Quick record</strong>
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Close recorder panel"
          style={{
            background: "none",
            border: "none",
            color: "rgba(0,0,0,0.55)",
            cursor: "pointer",
            fontSize: "1rem",
            lineHeight: 1,
            padding: "0 0.25rem",
          }}
        >
          ×
        </button>
      </div>
      <p
        style={{
          margin: "0 0 0.6rem",
          fontSize: "0.8rem",
          color: "rgba(0,0,0,0.62)",
          lineHeight: 1.4,
        }}
      >
        Sit, think, record. Up to 30 minutes. Saved memos land in{" "}
        <a href="/captures" style={{ color: "#1d4ed8" }}>
          captures
        </a>{" "}
        for triage.
      </p>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.6rem",
          marginBottom: "0.7rem",
          minHeight: 26,
        }}
      >
        {state === "idle" ? (
          <span
            style={{ fontSize: "0.85rem", color: "rgba(0,0,0,0.55)" }}
            data-testid="quick-recorder-idle"
          >
            Mic off — press start.
          </span>
        ) : (
          <RecordingPulse
            state={state === "paused" ? "paused" : "recording"}
            elapsedMs={elapsedMs}
          />
        )}
      </div>

      <div
        aria-hidden="true"
        style={{
          height: 4,
          background: "rgba(0,0,0,0.08)",
          borderRadius: 2,
          marginBottom: "0.8rem",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${ceilingPct}%`,
            height: "100%",
            background:
              ceilingPct > 85 ? "#d62828" : ceilingPct > 60 ? "#c89034" : "#1d4ed8",
            transition: "width 0.2s linear",
          }}
        />
      </div>

      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        {canStart ? (
          <button
            type="button"
            onClick={onStart}
            data-testid="quick-recorder-start"
            style={primaryBtn()}
          >
            Start recording
          </button>
        ) : (
          <>
            <button
              type="button"
              onClick={onPauseResume}
              disabled={!canPauseResume || uploading}
              style={secondaryBtn(uploading)}
            >
              {state === "paused" ? "Resume" : "Pause"}
            </button>
            <button
              type="button"
              onClick={onSave}
              disabled={!canSave}
              data-testid="quick-recorder-save"
              style={primaryBtn(!canSave)}
            >
              {uploading ? "Uploading…" : "Save"}
            </button>
          </>
        )}
        <button
          type="button"
          onClick={onDiscard}
          disabled={uploading}
          data-testid="quick-recorder-discard"
          style={destructiveBtn(uploading)}
        >
          Discard
        </button>
      </div>

      {errorMessage ? (
        <p
          role="alert"
          style={{
            margin: "0.75rem 0 0",
            fontSize: "0.8rem",
            color: "#9b1c1c",
            background: "#fff5f5",
            padding: "0.45rem 0.55rem",
            borderRadius: 6,
            border: "1px solid #f7d4d4",
          }}
        >
          {errorMessage}
        </p>
      ) : null}
      {lastSavedId ? (
        <p
          style={{
            margin: "0.75rem 0 0",
            fontSize: "0.8rem",
            color: "#0e7c3a",
          }}
        >
          Saved. <a href="/captures">Open captures →</a>
        </p>
      ) : null}
    </div>
  );
}

function primaryBtn(disabled = false): React.CSSProperties {
  return {
    padding: "0.45rem 0.85rem",
    borderRadius: 6,
    border: "1px solid #1d4ed8",
    background: disabled ? "#9bb1eb" : "#1d4ed8",
    color: "#fff",
    fontSize: "0.85rem",
    cursor: disabled ? "not-allowed" : "pointer",
    fontWeight: 500,
  };
}
function secondaryBtn(disabled = false): React.CSSProperties {
  return {
    padding: "0.45rem 0.85rem",
    borderRadius: 6,
    border: "1px solid rgba(0,0,0,0.18)",
    background: "#fff",
    color: "#1f1f1f",
    fontSize: "0.85rem",
    cursor: disabled ? "not-allowed" : "pointer",
  };
}
function destructiveBtn(disabled = false): React.CSSProperties {
  return {
    padding: "0.45rem 0.85rem",
    borderRadius: 6,
    border: "1px solid rgba(155,28,28,0.35)",
    background: "#fff",
    color: "#9b1c1c",
    fontSize: "0.85rem",
    cursor: disabled ? "not-allowed" : "pointer",
  };
}

/**
 * Round-trip the captured blob through the same signed-upload path
 * the upload page uses. Returns the server-assigned upload id so the
 * caller can link straight to the captures queue.
 */
export async function uploadVoiceMemo(
  result: RecordingResult,
): Promise<string> {
  const filename = `voice-memo-${new Date()
    .toISOString()
    .replace(/[:.]/g, "-")}.${result.extension}`;
  const audioDurationSec = Math.max(1, Math.round(result.durationMs / 1000));
  const prepBody = {
    filename,
    mimeType: result.mimeType.split(";")[0] || "audio/webm",
    size: result.blob.size,
    title: `Voice memo — ${new Date().toLocaleString()}`,
    description:
      "Stream-of-consciousness capture via the founder QuickRecorder. " +
      "quick_capture=true",
    sourceType: "voice_memo",
    visibility: "private",
    publishAsPost: false,
    audioDurationSec,
  };
  const prep = await fetch("/api/upload/signed/prepare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(prepBody),
  });
  const prepData = await prep.json();
  if (!prep.ok) {
    throw new Error(prepData?.error || `Prepare failed (${prep.status})`);
  }
  const { uploadId, signedUrl, headers: putHeaders } = prepData as {
    uploadId: string;
    signedUrl: string;
    headers?: Record<string, string>;
  };
  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", signedUrl);
    const ct =
      (putHeaders && putHeaders["Content-Type"]) ||
      result.mimeType ||
      "audio/webm";
    xhr.setRequestHeader("Content-Type", ct);
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else
        reject(
          new Error(
            `Upload failed (${xhr.status}): ${(xhr.responseText || "").slice(0, 180)}`,
          ),
        );
    };
    xhr.onerror = () =>
      reject(new Error("Upload failed: network/CORS error."));
    xhr.onabort = () => reject(new Error("Upload aborted"));
    xhr.send(result.blob);
  });
  const fin = await fetch(`/api/upload/signed/finalize/${uploadId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ audioDurationSec }),
  });
  const finData = await fin.json();
  if (!fin.ok) {
    throw new Error(finData?.error || `Finalize failed (${fin.status})`);
  }
  return uploadId;
}
