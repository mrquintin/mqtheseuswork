import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(__dirname, "..");
const pubPath = path.join(root, "content", "published.json");
const outDir = path.join(root, "public");

function escXml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function main() {
  fs.mkdirSync(outDir, { recursive: true });
  const bundle = JSON.parse(fs.readFileSync(pubPath, "utf8"));
  const base = (process.env.THESEUS_PUBLIC_SITE_URL || process.env.NEXT_PUBLIC_SITE_URL || "https://theseus.invalid")
    .toString()
    .replace(/\/+$/, "");
  const items = [...bundle.conclusions]
    .sort((a, b) => String(b.publishedAt).localeCompare(String(a.publishedAt)))
    .map((c) => {
      const title = c.payload?.conclusionText || c.slug;
      const linkPath = `/c/${encodeURIComponent(c.slug)}/v/${c.version}`;
      const abs = `${base}${linkPath}`;
      return {
        title,
        link: abs,
        guid: `${c.slug}@v${c.version}`,
        pubDate: new Date(c.publishedAt).toUTCString(),
        description: c.payload?.evidenceSummary || "",
      };
    });

  const rss = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Theseus — Published conclusions</title>
    <link>${escXml(`${base}/`)}</link>
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

  const atom = `<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Theseus — Published conclusions</title>
  <link href="${escXml(`${base}/`)}"/>
  <updated>${escXml(new Date(bundle.generatedAt || Date.now()).toISOString())}</updated>
  <id>${escXml(`${base}/atom.xml`)}</id>
  ${items
    .map(
      (it) => `
  <entry>
    <title>${escXml(it.title)}</title>
    <link href="${escXml(it.link)}"/>
    <id>${escXml(it.guid)}</id>
    <updated>${escXml(new Date(it.pubDate).toISOString())}</updated>
    <summary>${escXml(it.description)}</summary>
  </entry>`,
    )
    .join("\n")}
</feed>`;

  fs.writeFileSync(path.join(outDir, "feed.xml"), rss.trim() + "\n", "utf8");
  fs.writeFileSync(path.join(outDir, "atom.xml"), atom.trim() + "\n", "utf8");
}

main();
