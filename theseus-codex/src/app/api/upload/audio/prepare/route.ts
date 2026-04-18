/**
 * Legacy alias for /api/upload/signed/prepare.
 *
 * The audio-only path was renamed when non-audio files also gained
 * direct-to-storage uploads. This shim forwards to the generalized
 * endpoint so any external caller (old Dialectic builds, hard-coded
 * test scripts) continues to work while we migrate the UI. Delete
 * this file once no traffic hits it for a release cycle.
 */
export { POST } from "../../signed/prepare/route";
