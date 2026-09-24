"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export const STRATEGIES = ["anthropic_first", "openai_first", "alternate", "anthropic_only", "openai_only"] as const;
export type Strategy = (typeof STRATEGIES)[number];

/** Provider strategy (M7-02): which released provider answers first and whether the other one
 *  takes over when the budget is exhausted or the provider fails. "_only" never switches. */
export function RoutingSettings({ initial }: { initial: Strategy }) {
  const t = useTranslations("AiSettings");
  const [value, setValue] = useState<Strategy>(initial);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const change = async (next: Strategy) => {
    setValue(next);
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<{ strategy: Strategy }>("/api/bff/ai/routing", { method: "PUT", body: JSON.stringify({ strategy: next }) });
    setBusy(false);
    if (res.ok) setMessage(t("routingSaved"));
    else setError(res.message);
  };
  return (
    <section className={`${ui.card} flex flex-col gap-2`}>
      <h2 className="text-sm font-semibold">{t("routingTitle")}</h2>
      <label className="flex flex-col gap-1 sm:max-w-md">
        <span className={ui.label}>{t("routingLabel")}</span>
        <select className={ui.input} value={value} disabled={busy} onChange={(e) => void change(e.target.value as Strategy)}>
          {STRATEGIES.map((s) => (
            <option key={s} value={s}>
              {t(`routing.${s}`)}
            </option>
          ))}
        </select>
      </label>
      <p className="text-xs text-muted">{t(`routingHint.${value}`)}</p>
      {message ? <p className="text-xs text-success-fg">{message}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
