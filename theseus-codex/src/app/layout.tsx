import type { Metadata } from "next";
import "./globals.css";
import "./print.css";
import CRTOverlay from "@/components/CRTOverlay";
import { theseusIdentity } from "@/content/theseusIdentity";

export const metadata: Metadata = {
  title: theseusIdentity.metadata.title,
  description: theseusIdentity.metadata.description,
  alternates: {
    types: {
      "application/rss+xml": "/feed.xml",
      "application/atom+xml": "/atom.xml",
    },
  },
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
        <a className="skip-link" href="#main-content">
          Skip to content
        </a>
        <div id="main-content" tabIndex={-1}>
          {children}
        </div>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function () {
                function findSkipTarget() {
                  var root = document.getElementById("main-content");
                  if (!root) return null;
                  var main = root.querySelector("main");
                  if (!main) return root;

                  var firstChild = main.firstElementChild;
                  if (
                    firstChild &&
                    firstChild.tagName === "HEADER" &&
                    firstChild.querySelector('nav[aria-label="Public navigation"]')
                  ) {
                    return firstChild.nextElementSibling || main;
                  }

                  return main;
                }

                function activateSkipLink(event) {
                  var trigger = event.target && event.target.closest
                    ? event.target.closest(".skip-link")
                    : null;
                  if (!trigger) return;

                  var target = findSkipTarget();
                  if (!target) return;

                  event.preventDefault();
                  if (!target.hasAttribute("tabindex")) {
                    target.setAttribute("tabindex", "-1");
                  }
                  var previous = document.querySelector("[data-skip-focus-target]");
                  if (previous) previous.removeAttribute("data-skip-focus-target");
                  target.setAttribute("data-skip-focus-target", "true");
                  target.focus({ preventScroll: true });
                  target.scrollIntoView({ block: "start" });
                  if (window.history && window.history.pushState) {
                    window.history.pushState(null, "", "#main-content");
                  } else {
                    window.location.hash = "main-content";
                  }
                }

                document.addEventListener("click", activateSkipLink);
                document.addEventListener("keydown", function (event) {
                  if (event.key !== "Enter" && event.key !== " ") return;
                  activateSkipLink(event);
                });
              })();
            `,
          }}
        />
        {/* Sitewide scan-line + vignette overlay. Mounted last so it sits
            above all content in the stacking order. Respects
            prefers-reduced-motion internally. */}
        <CRTOverlay />
      </body>
    </html>
  );
}
