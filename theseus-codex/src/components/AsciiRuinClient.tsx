"use client";

import dynamic from "next/dynamic";
import type { ComponentProps } from "react";

const AsciiRuin = dynamic(() => import("./AsciiRuin"), {
  ssr: false,
  loading: () => (
    <div
      style={{
        height: 288,
        border: "1px dashed var(--border)",
        borderRadius: 2,
        opacity: 0.3,
      }}
    />
  ),
});

type Props = ComponentProps<typeof import("./AsciiRuin").default>;

export default function AsciiRuinClient(props: Props) {
  return <AsciiRuin {...props} />;
}
