"use client";

/** Dynamic-import wrapper for `ReviewScale`. See DashboardHearthClient for rationale. */

import dynamic from "next/dynamic";
import type { ReviewScaleProps } from "./ReviewScale";

const ReviewScale = dynamic(() => import("./ReviewScale"), { ssr: false });

export default function ReviewScaleClient(props: ReviewScaleProps) {
  return <ReviewScale {...props} />;
}
