import nextConfig, {
  appRedirects,
  legacyNavRedirects,
  retiredPublicRouteRedirects,
} from "../../next.config";

type RedirectRule = {
  source: string;
  destination: string;
  permanent: boolean;
};

function resolveRedirect(path: string, redirects: readonly RedirectRule[]) {
  for (const redirect of redirects) {
    if (!redirect.source.includes(":path*")) {
      if (redirect.source === path) return redirect.destination;
      continue;
    }

    const prefix = redirect.source.replace("/:path*", "");
    if (path === prefix || path.startsWith(prefix + "/")) {
      const rest = path.slice(prefix.length).replace(/^\/+/, "");
      return redirect.destination.replace(":path*", rest);
    }
  }
  return null;
}

describe("next.config legacy nav redirects", () => {
  it("exports the same redirect table used by Next", async () => {
    const redirects = await nextConfig.redirects?.();
    expect(redirects).toEqual(appRedirects);
  });

  it("permanently redirects the retired responses route to the homepage", () => {
    expect(resolveRedirect("/responses", appRedirects)).toBe("/");
    expect(retiredPublicRouteRedirects).toEqual([
      { source: "/responses", destination: "/", permanent: true },
    ]);
  });

  it.each([
    ["/conclusions", "/knowledge?tab=conclusions"],
    ["/explorer", "/knowledge?tab=explorer"],
    ["/library", "/knowledge?tab=library"],
    [
      "/publication",
      "/knowledge?tab=conclusions&notice=publication-retired",
    ],
    ["/peer-review", "/ops?panel=peer-review"],
    ["/peer-review/conclusion-1", "/ops?panel=peer-review&target=conclusion-1"],
    ["/contradictions", "/ops?panel=contradictions"],
    ["/post-mortem", "/ops?panel=post-mortem"],
    ["/adversarial", "/ops?panel=adversarial"],
    ["/decay", "/ops?panel=decay"],
    ["/rigor-gate", "/ops?panel=rigor-gate"],
    ["/rigor-gate/submission-1", "/ops?panel=rigor-gate&target=submission-1"],
    ["/open-questions", "/ops?panel=open-questions"],
    ["/q/review", "/ops?panel=layer-review"],
    ["/scoreboard", "/ops?panel=calibration"],
  ])("%s redirects to %s", (source, destination) => {
    expect(resolveRedirect(source, legacyNavRedirects)).toBe(destination);
  });
});
