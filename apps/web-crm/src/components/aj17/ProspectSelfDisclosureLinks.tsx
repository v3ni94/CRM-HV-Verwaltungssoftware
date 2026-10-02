"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type Link = { id: string; expires_at: string; submitted_at: string | null; consent_privacy: boolean };

/** Selbstauskunft Links je Interessent (GAI-420): `GET /letting/prospects/{id}/self-disclosure-links`.
 *  Zeigt Status und Ablauf, nie den Token (der Link erscheint nur bei der Erzeugung). */
export function ProspectSelfDisclosureLinks({ prospectId }: { prospectId: string }) {
  const t = useTranslations("Aj17.selfDisclosure");
  const [rows, setRows] = useState<Link[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = async () => {
    setError(null);
    const res = await bff<Link[]>(`/api/bff/letting/prospects/${prospectId}/self-disclosure-links`);
    if (res.ok) setRows(res.data);
    else setError(res.message);
  };
  if (rows === null) {
    return (
      <div data-testid="self-disclosure-links">
        <button type="button" className={ui.buttonSm} onClick={() => void load()}>
          {t("load")}
        </button>
        {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1 text-sm" data-testid="self-disclosure-links">
      <h4 className={ui.label}>{t("title")}</h4>
      {rows.length === 0 ? <p className="text-muted">{t("empty")}</p> : null}
      <ul>
        {rows.map((l) => {
          const expired = !l.submitted_at && new Date(l.expires_at).getTime() <= Date.now();
          return (
            <li key={l.id}>
              {l.submitted_at ? t("submitted", { date: formatDate(l.submitted_at) }) : expired ? t("expired") : t("open")}
              {" · "}
              {t("expires", { date: formatDate(l.expires_at) })}
            </li>
          );
        })}
      </ul>
      <p className={ui.help}>{t("help")}</p>
    </div>
  );
}
