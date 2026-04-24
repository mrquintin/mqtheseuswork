/**
 * Mint a Zenodo DOI for a published conclusion revision.
 * Without `THESEUS_ZENODO_TOKEN`, returns a deterministic preview DOI (not registered).
 */

type MintArgs = {
  title: string;
  description: string;
  creators?: { name: string }[];
};

function previewDoi(seed: string): { doi: string; recordId: string } {
  const h = seed.replace(/[^a-z0-9]+/gi, "").slice(0, 12) || "theseus";
  return { doi: `10.5281/zenodo.preview.${h}`, recordId: "" };
}

export async function mintZenodoDoi(args: MintArgs): Promise<{ doi: string; recordId: string }> {
  const token = process.env.THESEUS_ZENODO_TOKEN?.trim();
  if (!token) {
    return previewDoi(`${args.title}:${args.description.slice(0, 64)}`);
  }

  const creators =
    args.creators?.length ? args.creators : [{ name: process.env.THESEUS_ZENODO_CREATOR_NAME || "Theseus" }];

  try {
    const create = await fetch(`https://zenodo.org/api/deposit/depositions?access_token=${encodeURIComponent(token)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    if (!create.ok) {
      return previewDoi(args.title);
    }
    const created = (await create.json()) as { id?: number };
    const id = created.id;
    if (typeof id !== "number") {
      return previewDoi(args.title);
    }

    const put = await fetch(`https://zenodo.org/api/deposit/depositions/${id}?access_token=${encodeURIComponent(token)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        metadata: {
          title: args.title.slice(0, 250),
          upload_type: "publication",
          publication_type: "other",
          description: args.description.slice(0, 50_000),
          creators,
          access_right: "open",
          license: "cc-by-4.0",
        },
      }),
    });
    if (!put.ok) {
      return previewDoi(args.title);
    }

    const publish = await fetch(
      `https://zenodo.org/api/deposit/depositions/${id}/actions/publish?access_token=${encodeURIComponent(token)}`,
      { method: "POST" },
    );
    if (!publish.ok) {
      return previewDoi(args.title);
    }
    const published = (await publish.json()) as { doi?: string; id?: number; record_id?: number };
    const doi = typeof published.doi === "string" && published.doi ? published.doi : "";
    const recordId =
      typeof published.record_id === "number"
        ? String(published.record_id)
        : typeof published.id === "number"
          ? String(published.id)
          : "";
    if (!doi) {
      return previewDoi(args.title);
    }
    return { doi, recordId };
  } catch {
    return previewDoi(args.title);
  }
}
