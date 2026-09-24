"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

const MONEY = /^\d+([.,]\d{1,2})?$/;
const NUMBER = /^\d+([.,]\d+)?$/;
const dec = (v: string) => v.replace(",", ".");

/** New rent increase case (M26). Cap, comparison rent and dates are entered with their source;
 *  the system only computes and flags (M26-01). */
export function RentIncreaseCreate({ contracts }: { contracts: { id: string; label: string }[] }) {
  const t = useTranslations("RentIncrease");
  const router = useRouter();
  const [f, setF] = useState({
    contract_id: contracts[0]?.id ?? "",
    basis: "mietspiegel",
    target_rent: "",
    effective_date: "",
    reference_rent: "",
    cap_limit_percent: "",
    comparison_rent_per_sqm: "",
    source_note: "",
    justification: "",
    rent_index_name: "",
    rent_index_date: "",
  });
  const [flats, setFlats] = useState([{ address: "", rent_per_sqm: "" }]);
  const [expert, setExpert] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setF((p) => ({ ...p, [k]: e.target.value }));
  const valid = f.contract_id && MONEY.test(f.target_rent) && f.effective_date;
  const submit = async () => {
    setBusy(true);
    setError(null);
    const body: Record<string, string> = {
      contract_id: f.contract_id,
      basis: f.basis,
      target_rent: dec(f.target_rent),
      effective_date: f.effective_date,
    };
    if (f.reference_rent) body.reference_rent = dec(f.reference_rent);
    if (f.cap_limit_percent) body.cap_limit_percent = dec(f.cap_limit_percent);
    if (f.comparison_rent_per_sqm) body.comparison_rent_per_sqm = dec(f.comparison_rent_per_sqm);
    if (f.source_note.trim()) body.source_note = f.source_note.trim();
    const extra: Record<string, unknown> = {};
    if (f.justification) extra.justification = f.justification;
    if (f.justification === "mietspiegel") {
      if (f.rent_index_name.trim()) extra.rent_index_name = f.rent_index_name.trim();
      if (f.rent_index_date) extra.rent_index_date = f.rent_index_date;
    }
    if (f.justification === "vergleichswohnungen") {
      extra.comparison_flats = flats
        .filter((x) => x.address.trim() && NUMBER.test(x.rent_per_sqm))
        .map((x) => ({ address: x.address.trim(), rent_per_sqm: dec(x.rent_per_sqm) }));
    }
    if (f.justification === "gutachten" && expert) {
      const form = new FormData();
      form.append("file", expert);
      const doc = await bff<{ id: string }>("/api/bff/documents", { method: "POST", body: form });
      if (!doc.ok) {
        setBusy(false);
        setError(doc.message);
        return;
      }
      extra.expert_document_id = doc.data.id;
    }
    const res = await bff<{ id: string }>("/api/bff/letting/rent-increases", {
      method: "POST",
      body: JSON.stringify({ ...body, ...extra }),
    });
    setBusy(false);
    if (res.ok) router.push(`/vermietung/mieterhoehung/${res.data.id}`);
    else setError(res.message);
  };
  const field = (k: keyof typeof f, type = "text") => (
    <label className="flex flex-col gap-1">
      <span className={ui.label}>{t(`fields.${k}`)}</span>
      <input className={ui.input} type={type} value={f[k]} onChange={set(k)} />
    </label>
  );
  return (
    <div className="flex flex-col gap-2">
      <div className="grid gap-2 sm:grid-cols-4">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("fields.contract_id")}</span>
          <select className={ui.input} value={f.contract_id} onChange={set("contract_id")}>
            {contracts.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("fields.basis")}</span>
          <select className={ui.input} value={f.basis} onChange={set("basis")}>
            {["mietspiegel", "comparison", "modernization", "index", "graduated"].map((b) => (
              <option key={b} value={b}>
                {t(`basis.${b}`)}
              </option>
            ))}
          </select>
        </label>
        {field("target_rent")}
        {field("effective_date", "date")}
        {field("reference_rent")}
        {field("cap_limit_percent")}
        {field("comparison_rent_per_sqm")}
        {field("source_note")}
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("fields.justification")}</span>
          <select className={ui.input} value={f.justification} onChange={set("justification")}>
            <option value="">{t("justification.none")}</option>
            {["mietspiegel", "gutachten", "vergleichswohnungen"].map((j) => (
              <option key={j} value={j}>
                {t(`justification.${j}`)}
              </option>
            ))}
          </select>
        </label>
        {f.justification === "mietspiegel" ? (
          <>
            {field("rent_index_name")}
            {field("rent_index_date", "date")}
          </>
        ) : null}
        {f.justification === "gutachten" ? (
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("fields.expert_document")}</span>
            <input type="file" onChange={(e) => setExpert(e.target.files?.[0] ?? null)} />
          </label>
        ) : null}
      </div>
      {f.justification === "vergleichswohnungen" ? (
        <fieldset className="flex flex-col gap-2">
          <legend className={ui.label}>{t("flats")}</legend>
          {flats.map((x, i) => (
            <div key={i} className="grid gap-2 sm:grid-cols-2">
              <input
                className={ui.input}
                aria-label={t("flatAddress", { n: i + 1 })}
                value={x.address}
                onChange={(e) => setFlats((p) => p.map((y, k) => (k === i ? { ...y, address: e.target.value } : y)))}
              />
              <input
                className={ui.input}
                aria-label={t("flatRate", { n: i + 1 })}
                value={x.rent_per_sqm}
                onChange={(e) => setFlats((p) => p.map((y, k) => (k === i ? { ...y, rent_per_sqm: e.target.value } : y)))}
              />
            </div>
          ))}
          {flats.length < 20 ? (
            <button type="button" className={ui.button} onClick={() => setFlats((p) => [...p, { address: "", rent_per_sqm: "" }])}>
              {t("addFlat")}
            </button>
          ) : null}
        </fieldset>
      ) : null}
      <button type="button" className={ui.primary} onClick={submit} disabled={busy || !valid}>
        {t("createCheck")}
      </button>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** Process steps with evidence upload where the API requires a document (send, consent). */
export function RentIncreaseActions({ id, status }: { id: string; status: string }) {
  const t = useTranslations("RentIncrease");
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const act = async (action: string, needsDoc = false) => {
    setBusy(true);
    setError(null);
    let documentId: string | undefined;
    if (needsDoc) {
      if (!file) {
        setBusy(false);
        setError(t("docRequired"));
        return;
      }
      const form = new FormData();
      form.append("file", file);
      const doc = await bff<{ id: string }>("/api/bff/documents", { method: "POST", body: form });
      if (!doc.ok) {
        setBusy(false);
        setError(doc.message);
        return;
      }
      documentId = doc.data.id;
    }
    const res = await bff(`/api/bff/letting/rent-increases/${id}/actions`, {
      method: "POST",
      body: JSON.stringify(documentId ? { action, document_id: documentId } : { action }),
    });
    setBusy(false);
    if (res.ok) router.refresh();
    else setError(res.message);
  };
  const needsFile = status === "approved" || status === "sent";
  return (
    <div className="flex flex-col gap-2">
      {needsFile ? (
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{status === "approved" ? t("reviewDoc") : t("consentDoc")}</span>
          <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
      ) : null}
      <div className="flex flex-wrap gap-2">
        {status === "draft" ? (
          <button type="button" className={ui.primary} onClick={() => act("approve")} disabled={busy}>
            {t("actions.approve")}
          </button>
        ) : null}
        {status === "approved" ? (
          <button type="button" className={ui.primary} onClick={() => act("send", true)} disabled={busy}>
            {t("actions.send")}
          </button>
        ) : null}
        {status === "sent" ? (
          <>
            <button type="button" className={ui.primary} onClick={() => act("consent", true)} disabled={busy}>
              {t("actions.consent")}
            </button>
            <button type="button" className={ui.button} onClick={() => act("reject")} disabled={busy}>
              {t("actions.reject")}
            </button>
          </>
        ) : null}
        {status === "consented" ? (
          <button type="button" className={ui.primary} onClick={() => act("apply")} disabled={busy}>
            {t("actions.apply")}
          </button>
        ) : null}
        {status === "draft" || status === "approved" ? (
          <button type="button" className={ui.button} onClick={() => act("cancel")} disabled={busy}>
            {t("actions.cancel")}
          </button>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
