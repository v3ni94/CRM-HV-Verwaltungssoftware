"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type NumberFormatEntry = {
  scope: string;
  prefix: string;
  digits: number;
  start: number;
  year_based: boolean;
  locked: boolean;
  is_default: boolean;
  preview: string[];
};

type Channel = "post" | "email" | "portal";

/** GA01-07 und GA01-08: Standard-Zustellweg und Nummernkreise des Mandanten. */
export function TenantDefaultsAdmin({
  initialChannel,
  initialFormats,
}: {
  initialChannel: Channel;
  initialFormats: NumberFormatEntry[];
}) {
  const t = useTranslations("AA17");
  const [channel, setChannel] = useState<Channel>(initialChannel);
  const [formats, setFormats] = useState<NumberFormatEntry[]>(initialFormats);
  const [channelMsg, setChannelMsg] = useState<string | null>(null);
  const [formatMsg, setFormatMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const saveChannel = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setChannelMsg(null);
    setBusy(true);
    const res = await bff("/api/bff/tenant/delivery-default", {
      method: "PUT",
      body: JSON.stringify({ default_delivery_channel: channel }),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setChannelMsg(t("delivery.saved"));
  };

  const update = (scope: string, patch: Partial<NumberFormatEntry>) =>
    setFormats((rows) => rows.map((r) => (r.scope === scope ? { ...r, ...patch } : r)));

  const refreshPreview = async (row: NumberFormatEntry) => {
    const res = await bff<{ preview: string[] }>("/api/bff/tenant/number-formats/preview", {
      method: "POST",
      body: JSON.stringify({
        scope: row.scope,
        prefix: row.prefix,
        digits: row.digits,
        start: row.start,
        year_based: row.year_based,
      }),
    });
    if (res.ok) update(row.scope, { preview: res.data.preview });
  };

  const saveFormats = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setFormatMsg(null);
    setBusy(true);
    const body = Object.fromEntries(
      formats
        .filter((r) => !r.locked)
        .map((r) => [r.scope, { prefix: r.prefix, digits: r.digits, start: r.start, year_based: r.year_based }]),
    );
    const res = await bff<{ formats: NumberFormatEntry[] }>("/api/bff/tenant/number-formats", {
      method: "PUT",
      body: JSON.stringify({ formats: body }),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setFormats(res.data.formats);
    setFormatMsg(t("numbers.saved"));
  };

  return (
    <div className={ui.pageGap}>
      <form onSubmit={saveChannel} className={`${ui.card} flex flex-col gap-3`} aria-label={t("delivery.title")}>
        <h2 className={ui.h2}>{t("delivery.title")}</h2>
        <p className={ui.help}>{t("delivery.intro")}</p>
        <label htmlFor="aa17-channel" className={ui.label}>
          {t("delivery.title")}
        </label>
        <select id="aa17-channel" className={ui.input} value={channel} onChange={(e) => setChannel(e.target.value as Channel)}>
          {(["post", "email", "portal"] as const).map((c) => (
            <option key={c} value={c}>
              {t(`delivery.${c}`)}
            </option>
          ))}
        </select>
        {channelMsg ? <p className={ui.success}>{channelMsg}</p> : null}
        <div className={ui.formActions}>
          <button type="submit" className={ui.primary} disabled={busy}>
            {t("delivery.save")}
          </button>
        </div>
      </form>

      <form onSubmit={saveFormats} className={`${ui.card} flex flex-col gap-3`} aria-label={t("numbers.title")}>
        <h2 className={ui.h2}>{t("numbers.title")}</h2>
        <p className={ui.help}>{t("numbers.intro")}</p>
        <p className={ui.help}>{t("numbers.startHint")}</p>
        <div className={ui.tableScroll}>
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("numbers.scope")}</th>
                <th>{t("numbers.prefix")}</th>
                <th>{t("numbers.digits")}</th>
                <th>{t("numbers.start")}</th>
                <th>{t("numbers.yearBased")}</th>
                <th>{t("numbers.preview")}</th>
              </tr>
            </thead>
            <tbody>
              {formats.map((r) => (
                <tr key={r.scope}>
                  <td>
                    {t(`numbers.scopes.${r.scope}`)}
                    {r.locked ? <span className={ui.badgeWarning}>{t("numbers.locked")}</span> : null}
                  </td>
                  <td>
                    <input
                      className={ui.input}
                      aria-label={`${t("numbers.prefix")} ${t(`numbers.scopes.${r.scope}`)}`}
                      value={r.prefix}
                      maxLength={10}
                      disabled={r.locked}
                      onChange={(e) => update(r.scope, { prefix: e.target.value.toUpperCase() })}
                      onBlur={() => void refreshPreview(r)}
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      min={1}
                      max={12}
                      className={ui.input}
                      aria-label={`${t("numbers.digits")} ${t(`numbers.scopes.${r.scope}`)}`}
                      value={r.digits}
                      disabled={r.locked}
                      onChange={(e) => update(r.scope, { digits: Number(e.target.value) })}
                      onBlur={() => void refreshPreview(r)}
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      min={1}
                      className={ui.input}
                      aria-label={`${t("numbers.start")} ${t(`numbers.scopes.${r.scope}`)}`}
                      value={r.start}
                      disabled={r.locked}
                      onChange={(e) => update(r.scope, { start: Number(e.target.value) })}
                      onBlur={() => void refreshPreview(r)}
                    />
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`${t("numbers.yearBased")} ${t(`numbers.scopes.${r.scope}`)}`}
                      checked={r.year_based}
                      disabled={r.locked}
                      onChange={(e) => {
                        update(r.scope, { year_based: e.target.checked });
                        void refreshPreview({ ...r, year_based: e.target.checked });
                      }}
                    />
                  </td>
                  <td className={ui.mono}>{r.preview.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className={ui.notice}>{t("numbers.lockedHint")}</p>
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
        {formatMsg ? <p className={ui.success}>{formatMsg}</p> : null}
        <div className={ui.formActions}>
          <button type="submit" className={ui.primary} disabled={busy}>
            {t("numbers.save")}
          </button>
        </div>
      </form>
    </div>
  );
}
