import { listPublishedConclusionsForFeed } from "@/lib/conclusionsRead";
import { SITE } from "@/lib/site";

export const revalidate = 3600;

function escXml(s: string) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

export async function GET() {
  const rows = await listPublishedConclusionsForFeed();
  const items = rows.map((c) => {
    const title = c.payload?.conclusionText || c.slug;
    const linkPath = `/c/${encodeURIComponent(c.slug)}/v/${c.version}`;
    const abs = `${SITE}${linkPath}`;
    return {
      title,
      link: abs,
      pubDate: new Date(c.publishedAt).toUTCString(),
      description: c.payload?.evidenceSummary || "",
    };
  });

  const rss = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Theseus — Published conclusions</title>
    <link>${escXml(`${SITE}/`)}</link>
    <description>Chronological updates to published, versioned conclusions.</description>
    <language>en-us</language>
    ${items
      .map(
        (it) => `
    <item>
      <title>${escXml(it.title)}</title>
      <link>${escXml(it.link)}</link>
      <guid isPermaLink="true">${escXml(it.link)}</guid>
      <pubDate>${escXml(it.pubDate)}</pubDate>
      <description>${escXml(it.description)}</description>
    </item>`,
      )
      .join("\n")}
  </channel>
</rss>`;

  return new Response(rss.trim() + "\n", {
    headers: {
      "Content-Type": "application/rss+xml; charset=utf-8",
    },
  });
}
