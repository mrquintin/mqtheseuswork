import type { CSSProperties, ReactNode } from "react";

import PublicHeader from "@/components/PublicHeader";
import { getFounder } from "@/lib/auth";

export const metadata = { title: "Current events — Theseus" };

const containerStyle: CSSProperties = {
  maxWidth: "1040px",
  margin: "0 auto",
  paddingLeft: "1.25rem",
  paddingRight: "1.25rem",
};

export default async function CurrentsLayout({ children }: { children: ReactNode }) {
  const founder = await getFounder();

  return (
    <div
      style={{
        background: "var(--currents-bg)",
        minHeight: "100vh",
        color: "var(--currents-parchment)",
        paddingBottom: "4rem",
      }}
    >
      <PublicHeader authed={Boolean(founder)} />
      <header
        style={{
          padding: "2rem 0 1rem",
          borderBottom: "1px solid var(--currents-border)",
        }}
      >
        <div style={containerStyle}>
          <div
            style={{
              fontSize: "0.75rem",
              letterSpacing: "0.16em",
              textTransform: "uppercase",
              color: "var(--currents-amber)",
            }}
          >
            Theseus · live
          </div>
          <h1
            style={{
              fontFamily: "'EB Garamond', serif",
              fontSize: "1.85rem",
              margin: "0.4rem 0 0.2rem",
            }}
          >
            X posts, firm opinion.
          </h1>
          <p
            style={{
              color: "var(--currents-parchment-dim)",
              maxWidth: "60ch",
              margin: 0,
              fontSize: "0.95rem",
            }}
          >
            The firm watches live public signals, then publishes what its
            collective reasoning currently believes. When the firm cannot reach
            a responsible view, it abstains.
          </p>
        </div>
      </header>
      <div style={{ ...containerStyle, paddingTop: "1.6rem" }}>
        {children}
        <footer
          style={{
            marginTop: "3rem",
            paddingTop: "1.1rem",
            borderTop: "1px solid var(--currents-border)",
            fontSize: "0.78rem",
            lineHeight: 1.6,
            color: "var(--currents-parchment-dim)",
            fontStyle: "italic",
          }}
        >
          <p style={{ margin: 0, maxWidth: "52em" }}>
            Opinions on this page are generated from the firm's Noosphere of
            conclusions and claims. They are not legal or financial advice, and
            not an exhaustive survey of the firm's thinking. The firm abstains
            when its modeled judgment is not strong enough to publish; an
            abstention is not agreement with the observed post. Follow-up answers
            ask the Noosphere anew on each question rather than answering from
            memory.
          </p>
        </footer>
      </div>
    </div>
  );
}
