"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Created = { created: unknown[]; skipped: { journal_entry_id: string; reason: string }[] };

/** GAF-16: Kostenpositionen aus gebuchten Belegen eines Kontos übernehmen (nur im Entwurf). */
export function StatementCostsFromLedger({
  statementId,
  accounts,
  keys,
}: {
  statementId: string;
  accounts: { id: string; number: string; name: string }[];
  keys: { id: string; name: string }[];
}) {
  const t = useTranslations("HoaAF09.fromLedger");
  const router = useRouter();
  const [accountId, setAccountId] = useState("");
  const [keyId, setKeyId] = useState("");
  const [basis, setBasis] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Created | null>(null);
  const submit = async () => {
    setError(null);
    if (!accountId || !keyId || basis.trim().length < 3) {
      setError(t("required"));
      return;
    }
    setBusy(true);
    const res = await bff<Created>(`/api/bff/hoa/statements/${statementId}/costs/from-ledger`, {
      method: "POST",
      body: JSON.stringify({ account_id: accountId, allocation_key_id: keyId, basis: basis.trim() }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setResult(res.data);
    router.refresh();
  };
  return (
    <section className={ui.card} data-testid="costs-from-ledger">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className="mt-1 text-sm text-muted">{t("hint")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div className="mt-2 flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("account")}</span>
          <select className={ui.input} value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="" />
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.number} {a.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("key")}</span>
          <select className={ui.input} value={keyId} onChange={(e) => setKeyId(e.target.value)}>
            <option value="" />
            {keys.map((k) => (
              <option key={k.id} value={k.id}>
                {k.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("basis")}</span>
          <input className={ui.input} value={basis} onChange={(e) => setBasis(e.target.value)} />
        </label>
        <button type="button" className={ui.secondary} disabled={busy} onClick={() => void submit()}>
          {t("submit")}
        </button>
      </div>
      {result ? (
        <div className="mt-2 text-sm" role="status">
          <p>{t("created", { n: result.created.length })}</p>
          {result.skipped.length ? (
            <>
              <p>{t("skipped", { n: result.skipped.length })}</p>
              <ul className="list-inside list-disc text-muted">
                {result.skipped.map((s) => (
                  <li key={s.journal_entry_id}>{t(`reason.${s.reason}`)}</li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
