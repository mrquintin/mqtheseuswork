import type { Metadata } from "next";
import "./globals.css";
import CRTOverlay from "@/components/CRTOverlay";

export const metadata: Metadata = {
  title: "Theseus Codex",
  description:
    "Upload ideas, track methodology, build the communal brain. A disciplined instrument for firms that want to converge on better beliefs.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        {/*
          Theme bootstrap — must run before first paint to avoid a
          flash-of-wrong-theme when a returning visitor prefers light
          mode. The script order is:
            1. stored choice wins if present (localStorage "theme"),
            2. else the OS-level `prefers-color-scheme: light` hint,
            3. else dark (the default, matching the HTML attribute).
          We also wrap setting data-theme in a try so a locked-down
          iframe (no localStorage access) silently falls through to
          the inline default instead of a 500-byte SecurityError.
        */}
        <script
          dangerouslySetInnerHTML={{
            __html: `
              try {
                var stored = localStorage.getItem("theme");
                if (stored === "light" || stored === "dark") {
                  document.documentElement.setAttribute("data-theme", stored);
                } else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) {
                  document.documentElement.setAttribute("data-theme", "light");
                }
              } catch (e) {}
            `,
          }}
        />
      </head>
      <body className="crt-fade-in">
        {children}
        {/* Sitewide scan-line + vignette overlay. Mounted last so it sits
            above all content in the stacking order. Respects
            prefers-reduced-motion internally. */}
        <CRTOverlay />
      </body>
    </html>
  );
}
