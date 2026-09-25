"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { StatusPill, type StatusPillVariant } from "@/components/ui/StatusPill";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type FinApiAccount = {
  id: string;
  finapi_account_id: string;
  account_holder_name: string | null;
  account_type: string | null;
  account_name: string | null;
  property_bank_account_id: string | null;
  balance_booked: string | null;
  balance_available: string | null;
  balance_currency: string | null;
  balance_fetched_at: string | null;
  last_transactions_fetch_at: string | null;
};

type FinApiConnection = {
  id: string;
  bank_connection_id: string;
  bank_name: string;
  status: string;
  web_form_url: string | null;
  web_form_status: string | null;
  last_error: string | null;
  auto_update_enabled: boolean;
  accounts: FinApiAccount[];
};

const STATUS_VARIANT: Record<string, StatusPillVariant> = {
  not_configured: "neutral",
  web_form_pending: "warning",
  active: "success",
  update_required: "warning",
  error: "danger",
  consent_expired: "warning",
  disabled: "neutral",
};

/** "Bankverbindungen" (M11-finapi): finAPI Verbindungen mit Konten, Salden und Zuordnung.
 *  Neben dem bestehenden Kontoauszug-Upload auf /bank. Read only: keine Zahlungen. */
export function FinApiConnections() {
  const t = useTranslations("BankConnections");
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [connections, setConnections] = useState<FinApiConnection[]>([]);
  const [bankName, setBankName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    const cfg = await bff<{ configured: boolean }>("/api/v1/banking/finapi/config");
    setConfigured(cfg.ok ? cfg.data.configured : false);
    const list = await bff<FinApiConnection[]>("/api/v1/banking/finapi/connections");
    if (list.ok) setConnections(list.data);
  }

  useEffect(() => {
    load();
  }, []);

  async function act<T>(path: string, init?: RequestInit, okMessage?: string) {
    setBusy(true);
    setError(null);
    setMessage(null);
    const result = await bff<T>(path, init);
    setBusy(false);
    if (!result.ok) {
      setError(result.message || t("error"));
      return null;
    }
    if (okMessage) setMessage(okMessage);
    await load();
    return result.data;
  }

  async function connect() {
    const created = await act<FinApiConnection>("/api/v1/banking/finapi/connections", {
      method: "POST",
      body: JSON.stringify({ bank_name: bankName || t("connectPrompt") }),
    });
    if (created?.web_form_url) window.open(created.web_form_url, "_blank", "noopener");
    setBankName("");
  }

  if (configured === false) {
    return (
      <section className={ui.card}>
        <h2 className={ui.h2}>{t("title")}</h2>
        <p className="mt-2 text-sm text-muted">{t("notConfigured")}</p>
      </section>
    );
  }

  return (
    <section className={ui.card}>
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className="mt-1 text-sm text-muted">{t("intro")}</p>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      {message ? <p className={ui.notice}>{message}</p> : null}
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-sm">
          {t("connectPrompt")}
          <input className={ui.input} value={bankName} onChange={(e) => setBankName(e.target.value)} />
        </label>
        <button type="button" className={ui.primary} onClick={connect} disabled={busy}>
          {t("connect")}
        </button>
      </div>
      {connections.length === 0 ? (
        <p className="mt-3 text-sm text-muted">{t("noConnections")}</p>
      ) : (
        <div className="mt-3 flex flex-col gap-3">
          {connections.map((c) => (
            <div key={c.id} className="rounded-lg border border-border p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium">{c.bank_name}</span>
                <StatusPill variant={STATUS_VARIANT[c.status] ?? "neutral"} label={t(`status.${c.status}`)} />
              </div>
              {c.web_form_url && c.status === "web_form_pending" ? (
                <p className="mt-1 text-xs text-muted">{t("webFormHint")}</p>
              ) : null}
              {c.last_error ? <p className="mt-1 text-xs text-danger-fg">{c.last_error}</p> : null}
              <div className="mt-2 flex flex-wrap gap-2">
                {c.web_form_url ? (
                  <a href={c.web_form_url} target="_blank" rel="noopener" className={ui.buttonSm}>
                    {t("connect")}
                  </a>
                ) : null}
                <button
                  type="button"
                  className={ui.buttonSm}
                  disabled={busy}
                  onClick={() => act(`/api/v1/banking/finapi/connections/${c.id}/check`, { method: "POST" })}
                >
                  {t("check")}
                </button>
                <button
                  type="button"
                  className={ui.buttonSm}
                  disabled={busy}
                  onClick={async () => {
                    const updated = await act<FinApiConnection>(
                      `/api/v1/banking/finapi/connections/${c.id}/reauthorize`,
                      { method: "POST" }
                    );
                    if (updated?.web_form_url) window.open(updated.web_form_url, "_blank", "noopener");
                  }}
                >
                  {t("reauthorize")}
                </button>
                <button
                  type="button"
                  className={ui.buttonSm}
                  disabled={busy}
                  onClick={() => act(`/api/v1/banking/finapi/connections/${c.id}/disconnect`, { method: "POST" })}
                >
                  {t("disconnect")}
                </button>
              </div>
              {c.accounts.length > 0 ? (
                <div className="mt-2 overflow-x-auto">
                  <table className="mhvp-table">
                    <thead>
                      <tr>
                        <th>{t("title")}</th>
                        <th className="num">Saldo</th>
                        <th>{t("unassigned")}</th>
                        <th>{t("fetch")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {c.accounts.map((a) => (
                        <tr key={a.id}>
                          <td>{a.account_name ?? a.account_holder_name ?? a.finapi_account_id}</td>
                          <td className="num">
                            {a.balance_booked
                              ? formatEur(a.balance_booked) + (a.balance_currency !== "EUR" ? ` ${a.balance_currency}` : "")
                              : "–"}
                          </td>
                          <td>
                            {a.property_bank_account_id ? (
                              a.property_bank_account_id
                            ) : (
                              <AssignForm
                                label={t("assign")}
                                placeholder={t("assignPropertyBankAccountId")}
                                onAssign={(id) =>
                                  act(`/api/v1/banking/finapi/accounts/${a.id}/assign`, {
                                    method: "POST",
                                    body: JSON.stringify({ property_bank_account_id: id }),
                                  })
                                }
                              />
                            )}
                          </td>
                          <td>
                            <button
                              type="button"
                              className={ui.buttonSm}
                              disabled={busy || !a.property_bank_account_id}
                              onClick={() =>
                                act(`/api/v1/banking/finapi/accounts/${a.id}/fetch`, { method: "POST" }, t("queued"))
                              }
                            >
                              {t("fetch")}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function AssignForm({
  label,
  placeholder,
  onAssign,
}: {
  label: string;
  placeholder: string;
  onAssign: (id: string) => void;
}) {
  const [value, setValue] = useState("");
  return (
    <div className="flex gap-1">
      <input className={ui.input} placeholder={placeholder} value={value} onChange={(e) => setValue(e.target.value)} />
      <button type="button" className={ui.buttonSm} onClick={() => value && onAssign(value)}>
        {label}
      </button>
    </div>
  );
}
