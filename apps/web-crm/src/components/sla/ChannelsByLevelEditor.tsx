"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { ui } from "@/lib/ui";

import type { AlertChannel } from "./SlaSettings";

export type ChannelsByLevel = Record<string, AlertChannel[]>;

export const CHANNEL_LEVELS = [1, 2, 3] as const;
export const CHANNEL_ORDER: AlertChannel[] = ["internal", "email", "sms"];

/** Standard je Stufe, gespiegelt aus apps/api/src/mhvp/sla/channels.py (M35). */
export const DEFAULT_CHANNELS_BY_LEVEL: Record<(typeof CHANNEL_LEVELS)[number], AlertChannel[]> = {
  1: ["internal"],
  2: ["internal", "email"],
  3: ["internal", "email", "sms"],
};

/** Wirksame Kanäle je Stufe: Regelwert, sonst Standard. */
export function effectiveChannels(value: ChannelsByLevel | null | undefined): ChannelsByLevel {
  const out: ChannelsByLevel = {};
  for (const level of CHANNEL_LEVELS) {
    const configured = value?.[String(level)];
    out[String(level)] = configured ? [...configured] : [...DEFAULT_CHANNELS_BY_LEVEL[level]];
  }
  return out;
}

export function ChannelsByLevelEditor({
  value,
  canManage,
  onSave,
}: {
  value: ChannelsByLevel | null | undefined;
  canManage: boolean;
  onSave: (next: ChannelsByLevel) => Promise<boolean>;
}) {
  const t = useTranslations("Sla");
  const [draft, setDraft] = useState<ChannelsByLevel>(() => effectiveChannels(value));
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  const toggle = (level: number, channel: AlertChannel) => {
    setSaved(false);
    setDraft((prev) => {
      const key = String(level);
      const current = prev[key] ?? [];
      const has = current.includes(channel);
      const next = CHANNEL_ORDER.filter((c) => (c === channel ? !has : current.includes(c)));
      return { ...prev, [key]: next };
    });
  };

  const save = async () => {
    setBusy(true);
    const merged: ChannelsByLevel = { ...(value ?? {}), ...draft };
    const ok = await onSave(merged);
    setBusy(false);
    setSaved(ok);
  };

  return (
    <div className="flex flex-col gap-2" data-testid="channels-editor">
      <p className="text-xs font-medium">{t("channelEditor.title")}</p>
      <table className="text-xs">
        <thead>
          <tr>
            <th className="text-left font-medium">{t("channelEditor.level")}</th>
            {CHANNEL_ORDER.map((c) => (
              <th key={c} className="px-2 font-medium">
                {t(`channelEditor.${c}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {CHANNEL_LEVELS.map((level) => (
            <tr key={level}>
              <td>{t("channelEditor.levelN", { level })}</td>
              {CHANNEL_ORDER.map((c) => (
                <td key={c} className="px-2 text-center">
                  <input
                    type="checkbox"
                    aria-label={t("channelEditor.checkbox", { level, channel: t(`channelEditor.${c}`) })}
                    checked={(draft[String(level)] ?? []).includes(c)}
                    disabled={!canManage || busy}
                    onChange={() => toggle(level, c)}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-muted">{t("channelEditor.smsHint")}</p>
      {canManage ? (
        <div className="flex items-center gap-2">
          <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void save()}>
            {t("channelEditor.save")}
          </button>
          {saved ? <span className="text-xs text-muted">{t("channelEditor.saved")}</span> : null}
        </div>
      ) : null}
    </div>
  );
}
