import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { HandbookBlocks } from "@/components/hilfe/HandbookBlocks";
import { PageHeader } from "@/components/ui/PageHeader";
import { chapterBySlug, HANDBOOK } from "@/lib/handbook";

export function generateStaticParams() {
  return HANDBOOK.map((c) => ({ slug: c.slug }));
}

export default async function HilfeKapitelPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const chapter = chapterBySlug(slug);
  if (!chapter) notFound();
  const t = await getTranslations("Hilfe");
  const toc = chapter.blocks.filter((b) => b.t === "h" && b.level === 2);
  return (
    <div className="space-y-4">
      <Link href="/hilfe" className="text-sm underline">
        {t("back")}
      </Link>
      <PageHeader title={chapter.title} />
      {toc.length > 1 ? (
        <nav aria-label={t("toc")} className="text-sm">
          <ul className="flex flex-wrap gap-x-4 gap-y-1">
            {toc.map((b) => (
              <li key={b.t === "h" ? b.id : ""}>
                {b.t === "h" ? (
                  <a href={`#${b.id}`} className="underline">
                    {b.text}
                  </a>
                ) : null}
              </li>
            ))}
          </ul>
        </nav>
      ) : null}
      <HandbookBlocks blocks={chapter.blocks} />
    </div>
  );
}
