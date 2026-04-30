import type { CSSProperties, ReactNode } from "react";

export const metadata = { title: "Forecasts — Theseus" };

const containerStyle: CSSProperties = {
  maxWidth: "1120px",
  margin: "0 auto",
  paddingLeft: "1.25rem",
  paddingRight: "1.25rem",
};

export default function ForecastsLayout({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        background: "var(--forecasts-bg)",
        color: "var(--forecasts-parchment)",
        colorScheme: "dark",
        minHeight: "100vh",
        paddingBottom: "4rem",
      }}
    >
      <header
        style={{
          borderBottom: "1px solid var(--forecasts-border)",
          padding: "2rem 0 1rem",
        }}
      >
        <div style={containerStyle}>
          <div
            style={{
              color: "var(--forecasts-cool-gold)",
              fontSize: "0.75rem",
              letterSpacing: "0.16em",
              textTransform: "uppercase",
            }}
          >
            Theseus · forecasts
          </div>
          <h1
            style={{
              fontFamily: "'EB Garamond', serif",
              fontSize: "1.85rem",
              margin: "0.4rem 0 0.2rem",
            }}
          >
            Macro predictions, source-grounded.
          </h1>
          <p
            style={{
              color: "var(--forecasts-parchment-dim)",
              fontSize: "0.95rem",
              margin: 0,
              maxWidth: "62ch",
            }}
          >
            Forecasts are published only when the model can cite at least three
            verifiable sources. Probabilities are compared against the market's
            implied YES price, then scored when the market resolves.
          </p>
        </div>
      </header>
      <div style={{ ...containerStyle, paddingTop: "1.6rem" }}>
        {children}
        <footer
          style={{
            borderTop: "1px solid var(--forecasts-border)",
            color: "var(--forecasts-parchment-dim)",
            fontSize: "0.78rem",
            fontStyle: "italic",
            lineHeight: 1.6,
            marginTop: "3rem",
            paddingTop: "1.1rem",
          }}
        >
          <p style={{ margin: 0, maxWidth: "56em" }}>
            Forecasts are generated from the firm's published Noosphere and market
            data. They are not financial advice. Paper bets are shown publicly;
            live operator activity is separated from this reader-facing stream.
          </p>
        </footer>
      </div>
    </div>
  );
}
