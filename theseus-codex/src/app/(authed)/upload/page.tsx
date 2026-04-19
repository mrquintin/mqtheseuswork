import UploadForm from "@/components/UploadForm";
import SculptureBackdrop from "@/components/SculptureBackdrop";

/**
 * Upload page. Wrap the form in a relative-positioned container so the
 * Augustus Prima Porta backdrop can sit behind it on the left. See
 * SculptureBackdrop for the half-page backdrop pattern.
 *
 * Patron sculpture: **Augustus Prima Porta (SMK)**. The Codex's
 * upload action is called "Dedicatio" (dedication) on the form header,
 * and Augustus — an imperial patron figure captured in the oratorial
 * adlocutio pose — is the canonical classical figure of dedication.
 * He also reads as the most visually commanding in the set, which the
 * previous Discobolus (mid-throw, partially cropped) did not.
 *
 * Positioning notes
 * -----------------
 * The upload form is unusually tall (file drop, title, description,
 * type, visibility toggles, blog fields) and with the default
 * `verticalAnchor="center"` a backdrop sits directly behind the
 * mid-form region and reads as "concealed". Two small overrides:
 *
 *   verticalAnchor="top" + offsetY=-48
 *       Pins the figure to the top of the 80vh column and lifts it a
 *       further 48 px so the head sits nearer the page header instead
 *       of level with the form's fieldset.
 *
 *   offsetX=-96
 *       Shifts the figure 96 px to the left. Combined with the fade
 *       mask (which tracks the offset — see SculptureBackdrop) this
 *       pushes the figure's right edge well clear of the form's input
 *       column; `overflow: hidden` on the outer wrapper clips the part
 *       that leaves the viewport cleanly.
 *
 * The numbers were tuned against a 1440-wide viewport; on anything
 * narrower the SculptureBackdrop hides itself via its 768 px breakpoint.
 */
export default function UploadPage() {
  return (
    <div style={{ position: "relative", overflow: "hidden", minHeight: "80vh" }}>
      <SculptureBackdrop
        src="/sculptures/augustus.mesh.bin"
        side="left"
        yawSpeed={0.018}
        verticalAnchor="top"
        offsetY={-48}
        offsetX={-96}
      />
      <div style={{ position: "relative", zIndex: 1 }}>
        <UploadForm />
      </div>
    </div>
  );
}
