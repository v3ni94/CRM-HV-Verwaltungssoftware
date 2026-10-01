"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type TakeoverDefaults = { team_id: string | null; assignee_user_id: string | null };
export type TakeoverOption = { id: string; label: string };

/** Standardteam und Zuständiger der Übernahme-Tickets (V06-01). Leer heißt: keine Zuweisung.
 *  Ein gespeicherter Wert, der nicht in der Auswahl steht (fehlendes Leserecht, inaktiv), bleibt
 *  als Eintrag mit der Kennung erhalten, damit Speichern ihn nicht stillschweigend löscht. */
export function TakeoverTicketDefaultsCard({
  defaults,
  teams,
  members,
  canManage,
  incomplete,
}: {
  defaults: TakeoverDefaults;
  teams: TakeoverOption[];
  members: TakeoverOption[];
  canManage: boolean;
  incomplete: boolean;
}) {
  const t = useTranslations("TakeoverTicketDefaults");
  const router = useRouter();
  const teamId = useId();
  const userId = useId();
  const [team, setTeam] = useState(defaults.team_id ?? "");
  const [assignee, setAssignee] = useState(defaults.assignee_user_id ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const withCurrent = (opts: TakeoverOption[], current: string | null) =>
    current && !opts.some((o) => o.id === current) ? [...opts, { id: current, label: current }] : opts;
  const teamOptions = withCurrent(teams, defaults.team_id);
  const memberOptions = withCurrent(members, defaults.assignee_user_id);

  const save = async () => {
    setBusy(true);
    setError(null);
    setSaved(false);
    const res = await bff("/api/bff/onboarding/takeover-ticket-defaults", {
      method: "PUT",
      body: JSON.stringify({ team_id: team || null, assignee_user_id: assignee || null }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setSaved(true);
    router.refresh();
  };

  return (
    <div className={`${ui.card} flex flex-col gap-4`}>
      {incomplete ? <p className={ui.notice}>{t("unavailable")}</p> : null}
      {!canManage ? <p className={ui.notice}>{t("readonly")}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {saved ? (
        <p role="status" className={ui.success}>
          {t("saved")}
        </p>
      ) : null}
      <div>
        <label htmlFor={teamId} className={ui.label}>
          {t("team")}
        </label>
        <select id={teamId} className={ui.input} value={team} disabled={!canManage || busy} onChange={(e) => setTeam(e.target.value)}>
          <option value="">{t("none")}</option>
          {teamOptions.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor={userId} className={ui.label}>
          {t("assignee")}
        </label>
        <select id={userId} className={ui.input} value={assignee} disabled={!canManage || busy} onChange={(e) => setAssignee(e.target.value)}>
          <option value="">{t("none")}</option>
          {memberOptions.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
      {canManage ? (
        <div className={ui.formActions}>
          <button type="button" className={`${ui.primary} ${ui.actionFull}`} disabled={busy} onClick={() => void save()}>
            {t("save")}
          </button>
        </div>
      ) : null}
    </div>
  );
}
