"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import { bankAccountLabel, type BankAccountOption } from "./bankTypes";

type BankConfig = {
  property_bank_account_id: string;
  pain001_version: string;
  pain008_version: string;
  submission_channel: string;
  confirmed_with_bank_on: string | null;
  notes: string | null;
  supported: { pain001: string[]; pain008: string[]; channels: string[] };
};

/** Zahlungsformat je Bankkonto (GAI-403, M15-01): vereinbarte pain.001 und pain.008 Version und
 *  Einreichungsweg, mit Datum der Abstimmung mit der Bank. Es werden nur Versionen angeboten, die
 *  die Plattform erzeugen und prüfen kann. Speichern erzeugt keine Zahlungsdatei und löst keine
 *  Zahlung aus; Erzeugen und Einreichen bleiben bis G2 gesperrt. Schreiben braucht accounting:approve. */
export function PaymentBankConfigCard({ canApprove }: { canApprove: boolean }) {
  const t = useTranslations("BankActions.config");
  const [accounts, setAccounts] = useState<BankAccountOption[]>([]);
  const [accountId, setAccountId] = useState("");
  const [config, setConfig] = useState<BankConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      const res = await bff<BankAccountOption[]>("/api/bff/banking/accounts");
      if (res.ok) setAccounts(res.data);
      else setError(res.message);
    })();
  }, []);

  const choose = async (id: string) => {
    setAccountId(id);
    setConfig(null);
    setNotice(null);
    setError(null);
    if (!id) return;
    const res = await bff<BankConfig>(`/api/bff/banking/payment-bank-config/${id}`);
    if (res.ok) setConfig(res.data);
    else setError(res.message);
  };

  const patch = (p: Partial<BankConfig>) => setConfig((c) => (c ? { ...c, ...p } : c));

  const save = async () => {
    if (!config || !accountId) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    const res = await bff<BankConfig>(`/api/bff/banking/payment-bank-config/${accountId}`, {
      method: "PUT",
      body: JSON.stringify({
        pain001_version: config.pain001_version,
        pain008_version: config.pain008_version,
        submission_channel: config.submission_channel,
        confirmed_with_bank_on: config.confirmed_with_bank_on || null,
        notes: config.notes?.trim() ? config.notes.trim() : null,
      }),
    });
    setBusy(false);
    if (res.ok) {
      setConfig(res.data);
      setNotice(t("saved"));
    } else setError(res.message);
  };

  return (
    <section className={ui.card} data-testid="payment-bank-config">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className="mt-1 text-sm text-muted">{t("intro")}</p>
      <label className="mt-2 flex max-w-md flex-col gap-1">
        <span className={ui.label}>{t("account")}</span>
        <select className={ui.input} value={accountId} onChange={(e) => void choose(e.target.value)}>
          <option value="">{t("choose")}</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {bankAccountLabel(a)}
            </option>
          ))}
        </select>
      </label>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {notice ? <p className={ui.success}>{notice}</p> : null}
      {config ? (
        <div className="mt-3 grid max-w-2xl grid-cols-1 gap-2 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("pain001")}</span>
            <select className={ui.input} value={config.pain001_version} disabled={!canApprove} onChange={(e) => patch({ pain001_version: e.target.value })}>
              {config.supported.pain001.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("pain008")}</span>
            <select className={ui.input} value={config.pain008_version} disabled={!canApprove} onChange={(e) => patch({ pain008_version: e.target.value })}>
              {config.supported.pain008.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("channel")}</span>
            <select className={ui.input} value={config.submission_channel} disabled={!canApprove} onChange={(e) => patch({ submission_channel: e.target.value })}>
              {config.supported.channels.map((c) => (
                <option key={c} value={c}>
                  {t(`channel_${c}` as "channel_file")}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("confirmedOn")}</span>
            <input
              type="date"
              className={ui.input}
              value={config.confirmed_with_bank_on ?? ""}
              disabled={!canApprove}
              onChange={(e) => patch({ confirmed_with_bank_on: e.target.value || null })}
            />
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className={ui.label}>{t("notes")}</span>
            <textarea className={ui.input} maxLength={2000} value={config.notes ?? ""} disabled={!canApprove} onChange={(e) => patch({ notes: e.target.value })} />
          </label>
          {canApprove ? (
            <div className="sm:col-span-2">
              <button type="button" className={ui.primary} onClick={() => void save()} disabled={busy}>
                {t("save")}
              </button>
            </div>
          ) : (
            <p className="text-sm text-muted sm:col-span-2">{t("readOnly")}</p>
          )}
        </div>
      ) : null}
    </section>
  );
}
