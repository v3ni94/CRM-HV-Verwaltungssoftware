"use client";

import { useTranslations } from "next-intl";

import { SafeText } from "@/components/ui/SafeText";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type TicketCommentRow = {
  id?: string;
  body: string;
  internal: boolean;
  created_at: string;
  author_name?: string | null;
  author_contact_id?: string | null;
  document_ids?: string[];
};

/** Kommentare des Tickets mit Autor, Sichtbarkeit und Anzahl der angehängten Dokumente
 *  (Review 26.09.2026, M6). Kommentare aus dem Portal haben keinen Benutzer, sondern einen
 *  Kontakt als Autor. */
export function TicketComments({ comments }: { comments: TicketCommentRow[] }) {
  const t = useTranslations("Tickets");
  if (comments.length === 0) return <p className="text-sm text-muted">{t("noComments")}</p>;
  return (
    <ul className="flex min-w-0 flex-col gap-2 text-sm" data-testid="ticket-comments">
      {comments.map((c, i) => {
        const author = c.author_name ?? (c.author_contact_id ? t("portalAuthor") : t("unknownAuthor"));
        const docs = c.document_ids?.length ?? 0;
        return (
          <li key={c.id ?? i} className={`${ui.card} min-w-0`}>
            <div className="text-xs text-muted">
              {formatDateTime(c.created_at)} · {author} · {c.internal ? t("internal") : t("external")}
              {docs > 0 ? ` · ${t("commentDocuments", { count: docs })}` : ""}
            </div>
            <SafeText>{c.body}</SafeText>
          </li>
        );
      })}
    </ul>
  );
}
