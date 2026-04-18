import UploadForm from "@/components/UploadForm";
import SculptureBackdrop from "@/components/SculptureBackdrop";

/**
 * Upload page. Wrap the form in a relative-positioned container so the
 * Discobolus (MSR) backdrop can sit behind it on the left. See
 * SculptureBackdrop for the half-page backdrop pattern.
 */
export default function UploadPage() {
  return (
    <div style={{ position: "relative", overflow: "hidden", minHeight: "80vh" }}>
      <SculptureBackdrop
        src="/sculptures/discobolus-alt.mesh.bin"
        side="left"
        yawSpeed={0.018}
      />
      <div style={{ position: "relative", zIndex: 1 }}>
        <UploadForm />
      </div>
    </div>
  );
}
