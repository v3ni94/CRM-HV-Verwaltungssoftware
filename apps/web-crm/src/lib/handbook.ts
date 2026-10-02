import data from "./handbook.generated.json";

/** Handbook block model produced by scripts/build_handbook.py (docs/handbuch/*.md). */
export type HbBlock =
  | { t: "h"; level: number; text: string; id: string }
  | { t: "p" | "quote" | "code"; text: string }
  | { t: "ul" | "ol"; items: { depth: number; text: string }[] }
  | { t: "table"; head: string[]; rows: string[][] };

export type HbChapter = { slug: string; title: string; blocks: HbBlock[] };

export const HANDBOOK: HbChapter[] = (data as { chapters: HbChapter[] }).chapters;

export function chapterBySlug(slug: string): HbChapter | undefined {
  return HANDBOOK.find((c) => c.slug === slug);
}

const plain = (s: string) => s.replace(/[`*]/g, "").replace(/\[([^\]]*)\]\([^)]*\)/g, "$1");

function blockText(b: HbBlock): string {
  if ("items" in b) return b.items.map((i) => i.text).join(" ");
  if ("head" in b) return [...b.head, ...b.rows.flat()].join(" ");
  return b.text;
}

export type HbHit = { slug: string; title: string; anchor: string | null; heading: string | null; excerpt: string };

/** Full text search over chapters: every word must occur in a block; hit points to the section. */
export function searchHandbook(query: string, limit = 30): HbHit[] {
  const words = query.toLowerCase().split(/\s+/).filter((w) => w.length > 1);
  if (words.length === 0) return [];
  const hits: HbHit[] = [];
  for (const ch of HANDBOOK) {
    let section: { id: string; text: string } | null = null;
    for (const b of ch.blocks) {
      if (b.t === "h") section = { id: b.id, text: b.text };
      const text = plain(blockText(b));
      const low = (b.t === "h" ? b.text : text).toLowerCase();
      if (words.every((w) => low.includes(w))) {
        hits.push({
          slug: ch.slug,
          title: ch.title,
          anchor: section?.id ?? null,
          heading: section?.text ?? null,
          excerpt: text.length > 160 ? `${text.slice(0, 157)}...` : text,
        });
        if (hits.length >= limit) return hits;
      }
    }
  }
  return hits;
}
