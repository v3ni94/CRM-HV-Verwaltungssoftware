"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Status of the managing company's own legal entity and ledger (A32, `GET/POST /tenant/manager-entity`). */
export type ManagerEntityStatus = {
  status: "eingerichtet" | "nicht_eingerichtet";
  name: string | null;
  legal_entity_id: string | null;
  ledger_id: string | null;
  accounts_count: number;
  created: boolean;
};

export function ManagerEntitySetup({ initial, canUpdate }: { initial: ManagerEntityStatus | null; canUpdate: boolean }) {
  const t = useTranslations("ManagerEntitySetup");
  const [state, setState] = useState<ManagerEntityStatus | null>(initial);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const setUp = state?.status === "eingerichtet";

  async function create() {
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<ManagerEntityStatus>("/api/bff/tenant/manager-entity", { method: "POST" });
    setBusy(false);
    if (res.ok) {
      setState(res.data);
      setMessage(res.data.created ? t("created") : t("alreadySetUp"));
    } else setError(res.message);
  }

  return (
    <section className={ui.card} aria-labelledby="manager-entity-title">
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="manager-entity-title" className={ui.h2}>
            {t("title")}
          </h2>
          <span
            className={`rounded-md px-2 py-0.5 text-xs font-medium ${setUp ? "bg-success-bg text-success-fg" : "bg-surface text-muted"}`}
            data-testid="manager-entity-status"
          >
            {setUp ? t("status.setUp") : t("status.notSetUp")}
          </span>
        </div>
        <p className={ui.help}>{t("description")}</p>
        {state === null ? <p role="alert" className={ui.alert}>{t("loadError")}</p> : null}
        {setUp && state ? (
          <dl className="grid gap-1 text-sm sm:grid-cols-2">
            <dt className={ui.label}>{t("name")}</dt>
            <dd>{state.name}</dd>
            <dt className={ui.label}>{t("accounts")}</dt>
            <dd>{state.accounts_count}</dd>
          </dl>
        ) : null}
        {!setUp && canUpdate ? (
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className={ui.primary} disabled={busy} onClick={() => void create()}>
              {t("create")}
            </button>
          </div>
        ) : null}
        {!setUp && !canUpdate ? <p className="text-xs text-muted">{t("readOnly")}</p> : null}
        {message ? <span className="text-xs text-success-fg">{message}</span> : null}
        {error ? <span className={ui.error}>{error}</span> : null}
      </div>
    </section>
  );
}
