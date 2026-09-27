import Link from "next/link";
import { useTranslations } from "next-intl";

import { entityHref, type EntityType } from "@/lib/entity-links";
import { ui } from "@/lib/ui";

export type EntityLink = {
  /** Record type; decides the route and the default label. */
  type: EntityType;
  /** Record id; omitted links (no id) are skipped. */
  id?: string | null;
  /** Property of a building, ledger of a posting. */
  parentId?: string | null;
  /** Text shown instead of the type label, e.g. "Objekt 0815". */
  label?: string | null;
  /** Optional count, e.g. number of contracts. */
  count?: number | null;
  /** Explicit route; overrides the computed one. */
  href?: string | null;
};

/**
 * Verknüpfungsleiste (Ergänzung 5, rule 1): every detail page lists its related records as
 * links so that a user can jump and return without opening a context first. Links without
 * an id or route are dropped; the bar renders nothing when no link remains.
 */
export function EntityLinksBar({ links, testId = "entity-links" }: { links: EntityLink[]; testId?: string }) {
  const t = useTranslations("Common.links");
  const rows = links
    .map((link) => {
      const href = link.href ?? (link.id ? entityHref(link.type, link.id, link.parentId) : null);
      return href ? { ...link, href } : null;
    })
    .filter((link): link is EntityLink & { href: string } => link !== null);
  if (rows.length === 0) return null;
  return (
    <nav aria-label={t("title")} data-testid={testId} className="flex flex-wrap items-center gap-2">
      <span className={ui.label}>{t("title")}</span>
      {rows.map((link, index) => (
        <Link
          key={`${link.type}-${link.id ?? link.href}-${index}`}
          href={link.href}
          className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-0.5 text-xs font-medium text-fg transition hover:border-gold hover:bg-bg"
        >
          <span className="text-muted">{t(link.type)}</span>
          {link.label ? <span>{link.label}</span> : null}
          {link.count != null ? <span className="rounded-full bg-gold-soft px-1.5 text-[11px]">{link.count}</span> : null}
        </Link>
      ))}
    </nav>
  );
}
