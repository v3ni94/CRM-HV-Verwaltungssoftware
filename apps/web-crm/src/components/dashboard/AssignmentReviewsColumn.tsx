"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Review = { id: string; entity_type: string; entity_id: string; dimension: string; status: string; reason: string | null };

/** Work queue "Offene Zuordnungsprüfungen" (GAF-19, section 12): open questions about the
 *  assignment of tickets and mails (contact, property, unit). Reads the two open lists through
 *  the BFF; a list the caller may not read is left out. Decisions are made on the ticket or mail. */
export function AssignmentReviewsColumn() {
  const t = useTranslations("AssignmentReviews");
  const [tickets, setTickets] = useState<Review[] | null>(null);
  const [mails, setMails] = useState<Review[] | null>(null);
  useEffect(() => {
    let alive = true;
    void bff<Review[]>("/api/bff/tickets/assignment-reviews/open?limit=20").then((r) => alive && setTickets(r.ok ? (r.data ?? []) : []));
    void bff<Review[]>("/api/bff/mail/assignment-reviews/open?limit=20").then((r) => alive && setMails(r.ok ? (r.data ?? []) : []));
    return () => {
      alive = false;
    };
  }, []);
  const rows = [
    ...(tickets ?? []).map((r) => ({ ...r, href: `/tickets/${r.entity_id}`, kind: "ticket" })),
    ...(mails ?? []).map((r) => ({ ...r, href: "/mail", kind: "mail" })),
  ];
  return (
    <section className={ui.card} aria-labelledby="assignment-reviews-title" data-testid="assignment-reviews-column">
      <h2 id="assignment-reviews-title" className={ui.h2}>
        {t("title")}
      </h2>
      <p className="mt-1 text-xs text-subtle">{t("description")}</p>
      {tickets === null || mails === null ? (
        <p className="mt-4 text-sm text-muted">{t("loading")}</p>
      ) : rows.length === 0 ? (
        <p className="mt-4 text-sm text-muted">{t("empty")}</p>
      ) : (
        <ul className="mt-3 flex flex-col gap-2">
          {rows.map((r) => (
            <li key={`${r.kind}-${r.id}`}>
              <Link href={r.href} className={`${ui.cardLink} block !p-3 text-sm`}>
                <span className="font-medium">{t(`kind.${r.kind}`)}</span>, {t(`dimension.${r.dimension}`)}
                {r.reason ? <span className="block text-xs text-muted">{r.reason}</span> : null}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
