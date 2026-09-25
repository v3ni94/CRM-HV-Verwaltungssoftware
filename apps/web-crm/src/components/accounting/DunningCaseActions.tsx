"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Channel = "post" | "email" | "portal";

type Mahnbescheid = {
  id: string;
  case_id: string;
  hauptforderung: string;
  nebenforderungen: unknown[];
  status: string;
  hinweis: string;
};

/** Mahnhistorie: als versendet markieren (M16-09, einziger Weg, mit dem eine Stufe steigt,
 * solange Briefversand und Zustellnachweis nicht gebaut sind, M16-02) und, nur auf der
 * höchsten konfigurierten Mahnstufe, die Mahnbescheid-Vorbereitung samt JSON-Download
 * ("Vorbereitung, Prüfung durch Rechtsanwalt", docs/rules/M16-01.md). */
export function DunningCaseActions({
  caseId,
  status,
  isHighestLevel,
}: {
  caseId: string;
  status: string;
  isHighestLevel: boolean;
}) {
  const t = useTranslations("Dunning");
  const router = useRouter();
  const [channel, setChannel] = useState<Channel>("post");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [prep, setPrep] = useState<Mahnbescheid | null>(null);

  async function markSent() {
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/accounting/dunning-cases/${caseId}/mark-sent`, {
      method: "POST",
      body: JSON.stringify({ channel }),
    });
    setBusy(false);
    if (res.ok) router.refresh();
    else setError(res.message);
  }

  async function prepareMahnbescheid() {
    setBusy(true);
    setError(null);
    const res = await bff<Mahnbescheid>(
      `/api/bff/accounting/dunning-cases/${caseId}/mahnbescheid-vorbereitung`,
      { method: "POST" },
    );
    setBusy(false);
    if (res.ok) setPrep(res.data);
    else setError(res.message);
  }

  function download() {
    if (!prep) return;
    const blob = new Blob([JSON.stringify(prep, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `mahnbescheid-${caseId}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {status === "proposed" ? (
        <>
          <select
            className={`${ui.input} w-28`}
            value={channel}
            onChange={(e) => setChannel(e.target.value as Channel)}
            aria-label={t("markSentChannel")}
          >
            <option value="post">{t("channel.post")}</option>
            <option value="email">{t("channel.email")}</option>
            <option value="portal">{t("channel.portal")}</option>
          </select>
          <button type="button" className={ui.buttonSm} onClick={markSent} disabled={busy}>
            {t("markSent")}
          </button>
        </>
      ) : null}
      {isHighestLevel ? (
        prep ? (
          <button type="button" className={ui.buttonSm} onClick={download}>
            {t("mahnbescheidDownload")}
          </button>
        ) : (
          <button type="button" className={ui.buttonSm} onClick={prepareMahnbescheid} disabled={busy}>
            {t("mahnbescheid")}
          </button>
        )
      ) : null}
      {error ? (
        <span role="alert" className={ui.error}>
          {error}
        </span>
      ) : null}
    </div>
  );
}
