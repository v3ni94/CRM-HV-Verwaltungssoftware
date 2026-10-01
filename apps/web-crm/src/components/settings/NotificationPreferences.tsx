"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type Item = { kind: string; in_app: boolean; email: boolean; muted_until: string | null; mandatory: boolean };

/** Dauer der Stummschaltung in Stunden; "0" hebt sie auf. */
/** Message key of a kind: dots are not allowed in next-intl keys. */
const kindKey = (kind: string) => kind.replaceAll(".", "_");

const MUTE_HOURS = ["0", "1", "8", "24", "168"] as const;

/** Benachrichtigungseinstellungen je Benutzer (M23-04): Kanal in der App und per E-Mail je
 *  Art, Stummschaltung für alle Arten. Pflichtmeldungen (Fristen, SLA, Bankzustimmung) sind
 *  nicht abschaltbar. GET und PUT /workspace/notification-preferences. */
export function NotificationPreferences() {
  const t = useTranslations("NotificationSettings");
  const [items, setItems] = useState<Item[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [muteHours, setMuteHours] = useState<string>("0");

  const load = useCallback(async () => {
    const res = await bff<{ items: Item[] }>("/api/bff/workspace/notification-preferences");
    if (res.ok) setItems(res.data.items);
    else setError(res.message);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function update(kind: string, patch: Partial<Item>) {
    setMessage(null);
    setItems((prev) => (prev ?? []).map((i) => (i.kind === kind ? { ...i, ...patch } : i)));
  }

  async function save() {
    if (!items) return;
    setError(null);
    const hours = Number(muteHours);
    const payload = items
      .filter((i) => !i.mandatory)
      .map((i) => ({
        kind: i.kind,
        in_app: i.in_app,
        email: i.email,
        muted_until:
          i.kind === "*" ? (hours > 0 ? new Date(Date.now() + hours * 3600_000).toISOString() : null) : i.muted_until && new Date(i.muted_until) > new Date() ? i.muted_until : null,
      }));
    const res = await bff<{ items: Item[] }>("/api/bff/workspace/notification-preferences", {
      method: "PUT",
      body: JSON.stringify({ items: payload }),
    });
    if (res.ok) {
      setItems(res.data.items);
      setMuteHours("0");
      setMessage(t("saved"));
    } else setError(res.message);
  }

  if (items === null) {
    return error ? (
      <p role="alert" className={ui.alert}>
        {error}
      </p>
    ) : null;
  }
  const defaults = items.find((i) => i.kind === "*");
  const mutedUntil = defaults?.muted_until && new Date(defaults.muted_until) > new Date() ? defaults.muted_until : null;

  return (
    <section className={`${ui.card} flex flex-col gap-4`} aria-labelledby="notification-prefs-title" data-testid="notification-preferences">
      <h2 id="notification-prefs-title" className={ui.h2}>
        {t("channels")}
      </h2>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <label htmlFor="notification-mute" className="text-muted">
          {t("mute")}
        </label>
        <select id="notification-mute" value={muteHours} onChange={(e) => setMuteHours(e.target.value)} className={`${ui.input} w-48`}>
          {MUTE_HOURS.map((h) => (
            <option key={h} value={h}>
              {t(`muteOption.${h}`)}
            </option>
          ))}
        </select>
        {mutedUntil ? (
          <span className={ui.badgeWarning} data-testid="notification-muted-until">
            {t("mutedUntil", { date: formatDate(mutedUntil) })}
          </span>
        ) : null}
      </div>
      <p className={ui.help}>{t("muteHelp")}</p>
      <div className="overflow-x-auto">
        <table className={ui.table}>
          <thead>
            <tr>
              <th scope="col">{t("column.kind")}</th>
              <th scope="col">{t("column.inApp")}</th>
              <th scope="col">{t("column.email")}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.kind}>
                <td>
                  {i.kind === "*" ? t("defaultRow") : t.has(`kind.${kindKey(i.kind)}`) ? t(`kind.${kindKey(i.kind)}`) : i.kind}
                  {i.mandatory ? <span className={`${ui.badge} ml-2`}>{t("mandatory")}</span> : null}
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={i.in_app}
                    disabled={i.mandatory}
                    onChange={(e) => update(i.kind, { in_app: e.target.checked })}
                    aria-label={t("inAppFor", { kind: i.kind === "*" ? t("defaultRow") : t.has(`kind.${kindKey(i.kind)}`) ? t(`kind.${kindKey(i.kind)}`) : i.kind })}
                    data-testid={`pref-inapp-${i.kind}`}
                  />
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={i.email}
                    disabled={i.mandatory}
                    onChange={(e) => update(i.kind, { email: e.target.checked })}
                    aria-label={t("emailFor", { kind: i.kind === "*" ? t("defaultRow") : t.has(`kind.${kindKey(i.kind)}`) ? t(`kind.${kindKey(i.kind)}`) : i.kind })}
                    data-testid={`pref-email-${i.kind}`}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center gap-3">
        <button type="button" className={ui.button} onClick={() => void save()} data-testid="pref-save">
          {t("save")}
        </button>
        {message ? (
          <span role="status" className="text-sm text-muted">
            {message}
          </span>
        ) : null}
      </div>
    </section>
  );
}
