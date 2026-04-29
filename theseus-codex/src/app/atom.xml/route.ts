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
  const generatedAt = rows[0]?.publishedAt ?? new Date().toISOString();
  const items = rows.map((c) => {
    const title = c.payload?.conclusionText || c.slug;
    const linkPath = `/c/${encodeURIComponent(c.slug)}/v/${c.version}`;
    const abs = `${SITE}${linkPath}`;
    return {
      title,
      link: abs,
      guid: `${c.slug}@v${c.version}`,
      updated: new Date(c.publishedAt).toISOString(),
      description: c.payload?.evidenceSummary || "",
    };
  });

  const atom = `<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Theseus — Published conclusions</title>
  <link href="${escXml(`${SITE}/`)}"/>
  <updated>${escXml(new Date(generatedAt).toISOString())}</updated>
  <id>${escXml(`${SITE}/atom.xml`)}</id>
  ${items
    .map(
      (it) => `
  <entry>
    <title>${escXml(it.title)}</title>
    <link href="${escXml(it.link)}"/>
    <id>${escXml(it.guid)}</id>
    <updated>${escXml(it.updated)}</updated>
    <summary>${escXml(it.description)}</summary>
  </entry>`,
    )
    .join("\n")}
</feed>`;

  return new Response(atom.trim() + "\n", {
    headers: {
      "Content-Type": "application/atom+xml; charset=utf-8",
    },
  });
}
