"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Key = { id: string; code: string; name: string };

/** New special levy (W09). */
export function LevyCreate({ ledgerId, keys, basePath }: { ledgerId: string; keys: Key[]; basePath: string }) {
  const t = useTranslations("Levy");
  const router = useRouter();
  const [purpose, setPurpose] = useState("");
  const [total, setTotal] = useState("");
  const [key, setKey] = useState(keys.find((k) => k.code === "MEA")?.id ?? keys[0]?.id ?? "");
  const [firstDue, setFirstDue] = useState("");
  const [instalments, setInstalments] = useState("1");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const valid = purpose.trim().length >= 3 && /^\d+([.,]\d{1,2})?$/.test(total) && key && /^\d{4}-\d{2}$/.test(firstDue);
  const create = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<{ id: string }>("/api/bff/hoa/special-levies", {
      method: "POST",
      body: JSON.stringify({
        ledger_id: ledgerId,
        purpose: purpose.trim(),
        total: total.replace(",", "."),
        allocation_key_id: key,
        first_due: `${firstDue}-01`,
        instalments: Number(instalments),
      }),
    });
    setBusy(false);
    if (res.ok) router.push(`${basePath}/sonderumlage/${res.data.id}`);
    else setError(res.message);
  };
  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("purpose")}</span>
          <input className={ui.input} value={purpose} onChange={(e) => setPurpose(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("total")}</span>
          <input className={ui.input} inputMode="decimal" value={total} onChange={(e) => setTotal(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("key")}</span>
          <select className={ui.input} value={key} onChange={(e) => setKey(e.target.value)}>
            {keys.map((k) => (
              <option key={k.id} value={k.id}>
                {k.code} {k.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("firstDue")}</span>
          <input className={ui.input} type="month" value={firstDue} onChange={(e) => setFirstDue(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("instalments")}</span>
          <input className={ui.input} type="number" min={1} max={60} value={instalments} onChange={(e) => setInstalments(e.target.value)} />
        </label>
        <button type="button" className={ui.button} onClick={create} disabled={busy || !valid}>
          {t("create")}
        </button>
      </div>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </div>
  );
}

/** Calculation, resolution on the snapshot, application of instalments. */
export function LevySteps({
  id,
  status,
  legalEntityId,
  snapshotHash,
  purpose,
}: {
  id: string;
  status: string;
  legalEntityId: string;
  snapshotHash: string | null;
  purpose: string;
}) {
  const t = useTranslations("Levy");
  const router = useRouter();
  const [decidedOn, setDecidedOn] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const call = async <T,>(path: string, body?: unknown): Promise<T | null> => {
    setBusy(true);
    setError(null);
    const res = await bff<T>(`/api/bff/hoa/${path}`, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return null;
    }
    router.refresh();
    return res.data;
  };
  const resolve = async () => {
    const res = await call<{ id: string }>("resolutions", {
      legal_entity_id: legalEntityId,
      decided_on: decidedOn,
      subject: `${t("subject")}: ${purpose}`.slice(0, 2000),
      wording: t("wording", { purpose }),
      status: "positive",
      kind: "external",
      subject_type: "special_levy",
      subject_id: id,
      snapshot_hash: snapshotHash,
    });
    if (res) await call(`special-levies/${id}/resolve`, { resolution_id: res.id });
  };
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-end gap-2">
        {status === "draft" ? (
          <button type="button" className={ui.primary} onClick={() => call(`special-levies/${id}/calculate`)} disabled={busy}>
            {t("calculate")}
          </button>
        ) : null}
        {status === "calculated" ? (
          <>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("decidedOn")}</span>
              <input type="date" className={ui.input} value={decidedOn} onChange={(e) => setDecidedOn(e.target.value)} />
            </label>
            <button type="button" className={ui.primary} onClick={resolve} disabled={busy || !decidedOn || !snapshotHash}>
              {t("recordResolution")}
            </button>
          </>
        ) : null}
        {status === "resolved" ? (
          <button
            type="button"
            className={ui.primary}
            disabled={busy}
            onClick={() => window.confirm(t("confirmApply")) && call(`special-levies/${id}/apply`)}
          >
            {t("apply")}
          </button>
        ) : null}
      </div>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </div>
  );
}

/** Amendment resolution for an applied levy (W09-01, decided 24.09.2026): a new version is
 *  created; the difference per unit becomes an additional charge or a credit. The applied
 *  version stays unchanged. */
export function LevyAmend({ id, basePath }: { id: string; basePath: string }) {
  const t = useTranslations("Levy");
  const router = useRouter();
  const [total, setTotal] = useState("");
  const [due, setDue] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const valid = /^\d+([.,]\d{1,2})?$/.test(total) && /^\d{4}-\d{2}-01$/.test(due) && reason.trim().length >= 3;
  const submit = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<{ id: string }>(`/api/bff/hoa/special-levies/${id}/amend`, {
      method: "POST",
      body: JSON.stringify({ total: total.replace(",", "."), difference_due: due, reason: reason.trim() }),
    });
    setBusy(false);
    if (res.ok) router.push(`${basePath}/${res.data.id}`);
    else setError(res.message);
  };
  return (
    <section className={ui.card}>
      <h2 className="font-medium">{t("amend")}</h2>
      <p className="text-xs text-muted">{t("amendNote")}</p>
      <div className="mt-2 flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("newTotal")}</span>
          <input className={ui.input} value={total} onChange={(e) => setTotal(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("differenceDue")}</span>
          <input type="date" className={ui.input} value={due} onChange={(e) => setDue(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("reason")}</span>
          <input className={ui.input} value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
        <button type="button" className={ui.primary} disabled={busy || !valid} onClick={submit}>
          {t("createAmendment")}
        </button>
      </div>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </section>
  );
}
