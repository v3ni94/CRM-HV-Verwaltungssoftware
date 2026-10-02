"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

const CHOICES = ["yes", "no", "abstain"] as const;

type OwnVote = { agenda_item_id: string; contract_id: string; choice: string; cast_at: string; wording_sha256: string | null };
type Item = { id: string; position: number; title: string; proposal: string | null; wording_sha256: string; open: boolean; own_votes: OwnVote[] };
type Circular = { id: string; deadline: string; description: string | null; own_contract_ids: string[]; items: Item[] };
export type CircularListing = { enabled: boolean; note: string; circulars: Circular[] };

function deDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
}

/** Umlaufbeschluss im Eigentümerportal (AG07 / GAF-32): laufende Umlaufverfahren der eigenen
 *  Einheiten, eine Stimme je Einheit und Beschlussantrag, Nachweis mit Zeitpunkt und Prüfsumme
 *  des Beschlusstexts. Mandantenschalter und Freigabestufe G4 prüft die API; das Ergebnis stellt
 *  die Verwaltung fest. */
export function CircularVotePanel() {
  const t = useTranslations("PortalCircular");
  const [data, setData] = useState<CircularListing | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    const res = await bff<CircularListing>("/api/bff/portal/circular-resolutions");
    if (res.ok) setData(res.data);
    else if (res.status === 403) setForbidden(true);
    else setMessage(t("error", { message: res.message }));
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function vote(circularId: string, itemId: string, contractId: string, choice: string) {
    setBusy(true);
    setMessage(null);
    const res = await bff(`/api/bff/portal/circular-resolutions/${circularId}/vote`, {
      method: "POST",
      body: JSON.stringify({ agenda_item_id: itemId, contract_id: contractId, choice }),
    });
    setBusy(false);
    if (!res.ok) {
      setMessage(t("error", { message: res.message }));
      return;
    }
    setMessage(t("confirm"));
    await load();
  }

  if (forbidden) return <p className={ui.notice}>{t("ownersOnly")}</p>;
  if (!data) return message ? <p className={ui.notice}>{message}</p> : null;
  return (
    <div className="space-y-4">
      {message && <p className={ui.notice} role="status">{message}</p>}
      {!data.enabled && <p className={ui.notice}>{t("disabled")}</p>}
      {data.enabled && data.circulars.length === 0 && <p className="text-sm text-muted">{t("empty")}</p>}
      {data.circulars.map((c) => (
        <section key={c.id} className={ui.card}>
          <p className="text-sm text-muted">{t("deadline", { date: deDate(c.deadline) })}</p>
          {c.description && <p className="text-sm">{c.description}</p>}
          {c.items.map((item) => (
            <div key={item.id} className="mt-3 space-y-1">
              <h2 className="font-medium">
                {item.position}. {item.title}
              </h2>
              {item.proposal && <p className="whitespace-pre-line text-sm">{item.proposal}</p>}
              {c.own_contract_ids.map((unit) => {
                const own = item.own_votes.find((v) => v.contract_id === unit);
                return (
                  <div key={unit} className="text-sm">
                    <span className="mr-2">{t("unit", { id: unit.slice(0, 8) })}</span>
                    {own ? (
                      <span>
                        {t("voted", { choice: t(own.choice as (typeof CHOICES)[number]), at: deDate(own.cast_at) })}
                        <br />
                        <span className="break-all text-muted">{t("evidence", { hash: own.wording_sha256 ?? "" })}</span>
                      </span>
                    ) : item.open ? (
                      CHOICES.map((choice) => (
                        <button
                          key={choice}
                          type="button"
                          className={`${ui.buttonSm} mr-2`}
                          disabled={busy}
                          onClick={() => void vote(c.id, item.id, unit, choice)}
                        >
                          {t(choice)}
                        </button>
                      ))
                    ) : (
                      <span className="text-muted">{t("closed")}</span>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}
