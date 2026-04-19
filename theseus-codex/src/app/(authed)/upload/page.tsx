import UploadForm from "@/components/UploadForm";
import SculptureBackdrop from "@/components/SculptureBackdrop";

/**
 * Upload page. Wrap the form in a relative-positioned container so the
 * Discobolus (MSR) backdrop can sit behind it on the left. See
 * SculptureBackdrop for the half-page backdrop pattern.
 *
 * Positioning notes
 * -----------------
 * The upload form is unusually tall (file drop, title, description,
 * type, visibility toggles, blog fields) and with the default
 * `verticalAnchor="center"` the Discobolus sat exactly behind the
 * mid-form region and read as "concealed". Two small overrides:
 *
 *   verticalAnchor="top" + offsetY=-48
 *       Pins the figure to the top of the 80vh column and lifts it a
 *       further 48 px so the head sits nearer the page header instead
 *       of level with the form's fieldset, matching the "lifted further
 *       up" tune requested in UX feedback.
 *
 *   offsetX=-96
 *       Shifts the figure 96 px to the left. Combined with the fade
 *       mask this pushes the figure's right edge well clear of the
 *       form's input column; `overflow: hidden` on the outer wrapper
 *       clips the part that leaves the viewport cleanly.
 *
 * The numbers were tuned against a 1440-wide viewport; on anything
 * narrower the SculptureBackdrop hides itself via its 768 px breakpoint.
 */
export default function UploadPage() {
  return (
    <div style={{ position: "relative", overflow: "hidden", minHeight: "80vh" }}>
      <SculptureBackdrop
        src="/sculptures/discobolus-alt.mesh.bin"
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
