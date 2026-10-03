"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";
import { useBusy } from "@/lib/use-busy";

type Status = { enabled: boolean; version: string | null; artifact: Record<string, unknown> | null };

/** Lokales Klassifikationsmodell der Objektakte (M35): Status und Vorschlag je Prüffall. */
export function LocalModelStatus({ canPropose }: { canPropose: boolean }) {
  const t = useTranslations("ObjektakteRequired");
  const [status, setStatus] = useState<Status | null>(null);
  const [caseId, setCaseId] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { busy, guard } = useBusy();

  useEffect(() => {
    void bff<Status>("/api/bff/objektakte/local-model").then((res) => {
      if (res.ok) setStatus(res.data);
      else setError(res.message);
    });
  }, []);

  const propose = guard(async () => {
    setError(null);
    setResult(null);
    const res = await bff<Record<string, unknown>>(`/api/bff/objektakte/local-model/cases/${caseId.trim()}/propose`, { method: "POST", body: "{}" });
    if (!res.ok) return setError(res.message);
    setResult(JSON.stringify(res.data));
  });

  return (
    <section className={ui.card} aria-label={t("modelTitle")}>
      <h2 className="text-sm font-semibold">{t("modelTitle")}</h2>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {status ? (
        <p className="text-sm" data-testid="local-model-status">
          <span className={status.enabled ? ui.badgeSuccess : ui.badge}>{status.enabled ? t("modelOn") : t("modelOff")}</span>{" "}
          {status.version ? t("modelVersion", { version: status.version }) : t("modelNoVersion")}
        </p>
      ) : null}
      {canPropose && status?.enabled ? (
        <form
          className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            void propose();
          }}
        >
          <label className="flex flex-1 flex-col gap-1">
            <span className={ui.label}>{t("caseId")}</span>
            <input className={ui.input} value={caseId} onChange={(e) => setCaseId(e.target.value)} />
          </label>
          <button type="submit" className={ui.buttonSm} disabled={busy || !caseId.trim()}>
            {t("propose")}
          </button>
        </form>
      ) : null}
      {result ? (
        <pre className="mt-2 overflow-x-auto text-xs" data-testid="local-model-result">
          {result}
        </pre>
      ) : null}
    </section>
  );
}
