"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type CircularPortalVote = {
  id: string;
  meeting_id: string;
  item_title: string;
  contract_id: string;
  choice: "yes" | "no" | "abstain";
  cast_at: string;
  wording_sha256: string | null;
};

function deDateTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** Portalstimmen laufender Umlaufverfahren (AG07 / GAF-32), nur lesend: Einheit, Antrag, Stimme,
 *  Zeitpunkt und Prüfsumme des Beschlusstexts. Übernahme in die Ergebnisfeststellung bleibt eine
 *  Entscheidung der Verwaltung. */
export function CircularPortalVotes({ legalEntityId, owners }: { legalEntityId: string; owners: { id: string; label: string }[] }) {
  const t = useTranslations("HoaCircular");
  const [rows, setRows] = useState<CircularPortalVote[] | null>(null);

  useEffect(() => {
    let alive = true;
    void bff<CircularPortalVote[]>(`/api/bff/hoa/portal-circular-votes?legal_entity_id=${encodeURIComponent(legalEntityId)}`).then((res) => {
      if (alive && res.ok) setRows(res.data);
    });
    return () => {
      alive = false;
    };
  }, [legalEntityId]);

  if (!rows || rows.length === 0) return null;
  const label = (id: string) => owners.find((o) => o.id === id)?.label ?? id.slice(0, 8);
  return (
    <section className="flex flex-col gap-1" data-testid="circular-portal-votes">
      <h4 className={ui.label}>{t("portalVotes")}</h4>
      <p className={ui.help}>{t("portalVotesHint")}</p>
      <ul className="text-sm">
        {rows.map((r) => (
          <li key={r.id}>
            {t("portalVoteLine", { owner: label(r.contract_id), item: r.item_title, choice: t(`portalChoice.${r.choice}`), at: deDateTime(r.cast_at) })}
            <span className="block break-all text-xs text-muted">{t("portalVoteHash", { hash: r.wording_sha256 ?? "" })}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
