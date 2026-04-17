"use client";

import dynamic from "next/dynamic";
import type { ComponentProps } from "react";

const CascadeTree3D = dynamic(() => import("./CascadeTree3D"), {
  ssr: false,
  loading: () => (
    <div
      style={{
        height: 520,
        border: "1px dashed var(--border)",
        borderRadius: 2,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "var(--parchment-dim)",
      }}
    >
      <span className="mono" style={{ fontSize: "0.75rem" }}>
        ▰▰▱▱▱ assembling cascade…
      </span>
    </div>
  ),
});

type Props = ComponentProps<typeof import("./CascadeTree3D").default>;

export default function CascadeTree3DClient(props: Props) {
  return <CascadeTree3D {...props} />;
}
