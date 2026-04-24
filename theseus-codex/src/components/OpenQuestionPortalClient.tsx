"use client";

/** Dynamic-import wrapper for `OpenQuestionPortal`. See DashboardHearthClient for rationale. */

import dynamic from "next/dynamic";
import type { OpenQuestionPortalProps } from "./OpenQuestionPortal";

const OpenQuestionPortal = dynamic(() => import("./OpenQuestionPortal"), {
  ssr: false,
});

export default function OpenQuestionPortalClient(props: OpenQuestionPortalProps) {
  return <OpenQuestionPortal {...props} />;
}
