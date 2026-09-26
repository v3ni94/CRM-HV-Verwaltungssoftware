"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Automatischer Belegeingang (M14-05): startet beim Gmail-Abruf je neuem PDF-Anhang, der wie
 *  eine Rechnung aussieht, genau eine KI-Extraktion als Vorschlag. Standard aus. */
export function InvoiceIntakeAutoSettings({ initial }: { initial: boolean }) {
  const t = useTranslations("InvoiceIntakeAuto");
  const [enabled, setEnabled] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const change = async (next: boolean) => {
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<{ enabled: boolean }>("/api/bff/ai/invoice-intake-auto", {
      method: "PUT",
      body: JSON.stringify({ enabled: next }),
    });
    setBusy(false);
    if (res.ok) {
      setEnabled(res.data.enabled);
      setMessage(t("saved"));
    } else setError(res.message);
  };
  return (
    <section className={`${ui.card} flex flex-col gap-2`}>
      <h2 className="text-sm font-semibold">{t("title")}</h2>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={enabled} disabled={busy} onChange={(e) => void change(e.target.checked)} />
        {t("label")}
      </label>
      <p className="text-xs text-muted">{t("hint")}</p>
      <p className="text-xs text-muted">{t("costHint")}</p>
      {message ? <p className="text-xs text-success-fg">{message}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
