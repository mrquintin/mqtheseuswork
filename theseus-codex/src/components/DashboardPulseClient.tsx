"use client";

import dynamic from "next/dynamic";
import type { ComponentProps } from "react";

const DashboardPulse = dynamic(() => import("./DashboardPulse"), {
  ssr: false,
  loading: () => (
    <div
      style={{
        height: 168,
        borderTop: "1px solid var(--border)",
        borderBottom: "1px solid var(--border)",
      }}
    />
  ),
});

type Props = ComponentProps<typeof import("./DashboardPulse").default>;

export default function DashboardPulseClient(props: Props) {
  return <DashboardPulse {...props} />;
}
