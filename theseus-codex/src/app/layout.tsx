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
        <script
          dangerouslySetInnerHTML={{
            __html: `
              try {
                const t = localStorage.getItem("theme");
                if (t) document.documentElement.setAttribute("data-theme", t);
              } catch {}
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
