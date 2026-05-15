"use client";

/**
 * Browser audio capture for the founder QuickRecorder.
 *
 * Wraps MediaRecorder with the bits the recorder UI needs:
 *
 *   - VAD-style trim of the leading silence so the first ~100ms of
 *     dead air before the founder actually started talking does not
 *     contaminate the transcript. We do this client-side because the
 *     bytes don't leave the browser at all on a discard, and the
 *     trimmed blob is what gets uploaded.
 *   - A 30-minute hard ceiling. Voice memos that run past that aren't
 *     "stream of consciousness" any more — they're recordings of
 *     meetings or talks and belong in the existing upload flow.
 *   - Pause / resume, since the founder might want to gather a thought
 *     mid-memo without ending the capture.
 *   - Container fallback: webm/opus by default, mp4/aac on Safari
 *     (which has historically only supported MediaRecorder via the
 *     MP4 container). Whatever the browser actually gave us is what
 *     we upload — the noosphere audio extractor handles all of them.
 *
 * The module is deliberately tiny and dependency-free; the UI in
 * QuickRecorder.tsx drives it.
 */

export const MAX_RECORDING_MS = 30 * 60 * 1000; // 30 minutes

/** Mime types we'll try in order. First one the browser accepts wins. */
const CANDIDATE_MIMES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/mp4;codecs=mp4a.40.2",
  "audio/mp4",
];

export interface RecordingResult {
  blob: Blob;
  mimeType: string;
  durationMs: number;
  /** File extension matching the chosen container, without the dot. */
  extension: string;
}

export type RecorderState =
  | "idle"
  | "requesting-permission"
  | "recording"
  | "paused"
  | "stopping"
  | "error";

export interface RecorderEvents {
  onStateChange?: (state: RecorderState) => void;
  /** Fired ~10x/sec while recording so the UI can render the timer. */
  onTick?: (elapsedMs: number) => void;
  /** Fired when the hard ceiling is hit and we auto-stop. */
  onCeilingReached?: () => void;
  onError?: (err: Error) => void;
}

function pickMimeType(): string | null {
  if (typeof MediaRecorder === "undefined") return null;
  for (const mime of CANDIDATE_MIMES) {
    if (MediaRecorder.isTypeSupported(mime)) return mime;
  }
  return null;
}

function extensionFor(mimeType: string): string {
  if (mimeType.startsWith("audio/webm")) return "webm";
  if (mimeType.startsWith("audio/ogg")) return "ogg";
  if (mimeType.startsWith("audio/mp4")) return "m4a";
  return "bin";
}

export class AudioRecorder {
  private mediaRecorder: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private chunks: Blob[] = [];
  private mimeType: string = "";
  private startedAt: number = 0;
  private accumulatedMs: number = 0;
  private pausedAt: number = 0;
  private tickHandle: ReturnType<typeof setInterval> | null = null;
  private ceilingHandle: ReturnType<typeof setTimeout> | null = null;
  private state: RecorderState = "idle";
  private events: RecorderEvents;
  private resolveStop: ((r: RecordingResult) => void) | null = null;
  private rejectStop: ((e: Error) => void) | null = null;

  constructor(events: RecorderEvents = {}) {
    this.events = events;
  }

  getState(): RecorderState {
    return this.state;
  }

  /** Elapsed ms of *recorded* audio (excludes paused time). */
  elapsedMs(): number {
    if (this.state === "recording") {
      return this.accumulatedMs + (Date.now() - this.startedAt);
    }
    return this.accumulatedMs;
  }

  async start(): Promise<void> {
    if (this.state !== "idle") {
      throw new Error(
        `AudioRecorder.start() called in state '${this.state}'; ` +
          `caller must reach 'idle' first.`,
      );
    }
    const mime = pickMimeType();
    if (!mime) {
      const err = new Error(
        "This browser doesn't support MediaRecorder with any of the " +
          "audio formats Theseus knows how to ingest. Try Chrome, Firefox, " +
          "or a recent Safari.",
      );
      this.setState("error");
      this.events.onError?.(err);
      throw err;
    }
    this.setState("requesting-permission");
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
    } catch (err) {
      const wrapped =
        err instanceof Error
          ? err
          : new Error(`Microphone permission failed: ${String(err)}`);
      this.setState("error");
      this.events.onError?.(wrapped);
      throw wrapped;
    }
    this.mimeType = mime;
    this.chunks = [];
    this.accumulatedMs = 0;
    this.mediaRecorder = new MediaRecorder(this.stream, { mimeType: mime });
    this.mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) this.chunks.push(event.data);
    };
    this.mediaRecorder.onerror = (event) => {
      const err =
        (event as unknown as { error?: Error }).error ??
        new Error("MediaRecorder error");
      this.setState("error");
      this.events.onError?.(err);
      if (this.rejectStop) {
        this.rejectStop(err);
        this.rejectStop = null;
        this.resolveStop = null;
      }
    };
    this.mediaRecorder.onstop = () => this.finalize();
    // Slice every second so the chunks list grows during the recording
    // — keeps memory pressure bounded if the founder records the full
    // 30 minutes.
    this.mediaRecorder.start(1000);
    this.startedAt = Date.now();
    this.setState("recording");
    this.startTimers();
  }

  pause(): void {
    if (this.state !== "recording" || !this.mediaRecorder) return;
    this.mediaRecorder.pause();
    this.accumulatedMs += Date.now() - this.startedAt;
    this.pausedAt = Date.now();
    this.stopTimers();
    this.setState("paused");
  }

  resume(): void {
    if (this.state !== "paused" || !this.mediaRecorder) return;
    this.mediaRecorder.resume();
    this.startedAt = Date.now();
    this.setState("recording");
    this.startTimers();
  }

  /**
   * Stop recording and resolve with the final blob. The returned
   * promise rejects if MediaRecorder errors out before producing data.
   */
  stop(): Promise<RecordingResult> {
    if (
      this.state !== "recording" &&
      this.state !== "paused"
    ) {
      return Promise.reject(
        new Error(`AudioRecorder.stop() called in state '${this.state}'`),
      );
    }
    if (this.state === "recording") {
      this.accumulatedMs += Date.now() - this.startedAt;
    }
    this.stopTimers();
    this.setState("stopping");
    return new Promise<RecordingResult>((resolve, reject) => {
      this.resolveStop = resolve;
      this.rejectStop = reject;
      try {
        this.mediaRecorder?.stop();
      } catch (err) {
        reject(err instanceof Error ? err : new Error(String(err)));
      }
    });
  }

  /**
   * Discard the recording and release the mic. The blob never leaves
   * the browser. Safe to call in any state.
   */
  discard(): void {
    this.stopTimers();
    if (
      this.mediaRecorder &&
      (this.mediaRecorder.state === "recording" ||
        this.mediaRecorder.state === "paused")
    ) {
      try {
        this.mediaRecorder.ondataavailable = null;
        this.mediaRecorder.onstop = null;
        this.mediaRecorder.stop();
      } catch {
        /* ignore — discard is best-effort */
      }
    }
    this.releaseStream();
    this.chunks = [];
    this.mediaRecorder = null;
    this.accumulatedMs = 0;
    if (this.rejectStop) {
      this.rejectStop(new Error("Recording discarded"));
      this.rejectStop = null;
      this.resolveStop = null;
    }
    this.setState("idle");
  }

  private finalize(): void {
    const durationMs = this.accumulatedMs;
    const rawBlob = new Blob(this.chunks, { type: this.mimeType });
    // VAD-style trim: drop the first chunk if it's tiny (< ~80ms of
    // data at typical opus bitrates is ~1 KB). Anything larger is
    // already speech-bearing. This is an intentionally crude trim —
    // a full VAD belongs server-side in the transcription step.
    const trimmed = trimLeadingSilence(this.chunks, this.mimeType);
    const blob = trimmed ?? rawBlob;
    const result: RecordingResult = {
      blob,
      mimeType: this.mimeType,
      durationMs,
      extension: extensionFor(this.mimeType),
    };
    this.releaseStream();
    this.mediaRecorder = null;
    this.chunks = [];
    this.setState("idle");
    if (this.resolveStop) {
      this.resolveStop(result);
      this.resolveStop = null;
      this.rejectStop = null;
    }
  }

  private startTimers(): void {
    this.tickHandle = setInterval(() => {
      this.events.onTick?.(this.elapsedMs());
    }, 100);
    const remaining = Math.max(0, MAX_RECORDING_MS - this.elapsedMs());
    this.ceilingHandle = setTimeout(() => {
      this.events.onCeilingReached?.();
      this.stop().catch(() => {
        /* ceiling-stop best-effort — onError already fired */
      });
    }, remaining);
  }

  private stopTimers(): void {
    if (this.tickHandle) {
      clearInterval(this.tickHandle);
      this.tickHandle = null;
    }
    if (this.ceilingHandle) {
      clearTimeout(this.ceilingHandle);
      this.ceilingHandle = null;
    }
  }

  private releaseStream(): void {
    if (this.stream) {
      this.stream.getTracks().forEach((t) => t.stop());
      this.stream = null;
    }
  }

  private setState(next: RecorderState): void {
    this.state = next;
    this.events.onStateChange?.(next);
  }
}

/**
 * Drop a silent SECOND chunk while preserving the container header.
 *
 * MediaRecorder.start(1000) emits chunks at 1-second intervals; the
 * FIRST chunk contains the webm/mp4 container header plus the first
 * second of audio, so it's always large and we must keep it intact —
 * dropping it would yield an unplayable file. The earliest place a
 * realistic "silence" chunk can appear is at index 1.
 *
 * The trim is conservative: we only splice out chunk[1] when it's
 * tiny enough that the data cannot contain speech (< ~1.5 KB ≈ <120 ms
 * of opus at default MediaRecorder bitrates). Anything larger almost
 * certainly contains a syllable and we leave the recording intact.
 * Full VAD belongs server-side in the transcription step; this is
 * just an upload-time win for the common case of the founder
 * fumbling the start button.
 */
function trimLeadingSilence(chunks: Blob[], mimeType: string): Blob | null {
  if (chunks.length < 3) return null;
  const SILENCE_BYTES = 1500;
  if (chunks[1].size >= SILENCE_BYTES) return null;
  return new Blob([chunks[0], ...chunks.slice(2)], { type: mimeType });
}

/** Test-only helper exposing the trim heuristic for unit tests. */
export const _testing = { trimLeadingSilence, pickMimeType, extensionFor };
