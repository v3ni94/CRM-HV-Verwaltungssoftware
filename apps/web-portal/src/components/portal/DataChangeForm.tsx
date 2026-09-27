"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Kind = "address" | "phone" | "email" | "bank_account";
const KINDS: Kind[] = ["address", "phone", "email", "bank_account"];

const FIELDS: Record<Kind, string[]> = {
  address: ["street", "house_number", "postal_code", "city"],
  phone: ["number"],
  email: ["email"],
  bank_account: ["iban"],
};

/** Datenänderung (M21): Anschrift, Telefon, E-Mail oder Bankverbindung als Vorschlag; die
 *  Verwaltung prüft und übernimmt die Änderung. Anschrift (M21-02) mit Gültigkeitsdatum und
 *  optionalem Nachweis (eigener Upload über /portal/uploads, als document_id übergeben). */
export function DataChangeForm() {
  const t = useTranslations("DataChange");
  const tPortal = useTranslations("Portal");
  const [kind, setKind] = useState<Kind>("address");
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [validFrom, setValidFrom] = useState("");
  const [evidence, setEvidence] = useState<File | null>(null);

  function setField(name: string, v: string) {
    setValues((prev) => ({ ...prev, [name]: v }));
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const payload: Record<string, string> = {};
    for (const name of FIELDS[kind]) payload[name] = (values[name] ?? "").trim();
    if (Object.values(payload).every((v) => !v)) {
      setError(t("submitted"));
      return;
    }
    if (kind === "address") {
      if (!payload.street || !payload.postal_code || !payload.city || !validFrom) {
        setError(t("errorAddress"));
        return;
      }
      payload.valid_from = validFrom;
    }
    setBusy(true);
    if (kind === "address" && evidence) {
      const form = new FormData();
      form.append("file", evidence, evidence.name);
      const upload = await bff<{ id: string }>("/api/bff/portal/uploads", { method: "POST", body: form });
      if (!upload.ok) {
        setBusy(false);
        setError(upload.message);
        return;
      }
      payload.document_id = upload.data.id;
    }
    const result = await bff<{ id: string }>("/api/bff/portal/change-requests", {
      method: "POST",
      body: JSON.stringify({ kind, payload }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setDone(true);
    setValues({});
    setValidFrom("");
    setEvidence(null);
  }

  return (
    <form onSubmit={onSubmit} noValidate className={`${ui.card} flex flex-col gap-3`}>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {done ? <p className={ui.success}>{t("submitted")}</p> : null}
      <div>
        <label htmlFor="change-kind" className={ui.label}>
          {t("kind")}
        </label>
        <select
          id="change-kind"
          className={ui.input}
          value={kind}
          onChange={(e) => {
            setKind(e.target.value as Kind);
            setValues({});
          }}
        >
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {t(`kindOptions.${k}`)}
            </option>
          ))}
        </select>
      </div>
      {FIELDS[kind].map((name) => (
        <div key={name}>
          <label htmlFor={`field-${name}`} className={ui.label}>
            {t(`fields.${name}`)}
          </label>
          <input
            id={`field-${name}`}
            className={ui.input}
            value={values[name] ?? ""}
            onChange={(e) => setField(name, e.target.value)}
          />
        </div>
      ))}
      {kind === "address" ? (
        <>
          <div>
            <label htmlFor="field-valid_from" className={ui.label}>
              {t("fields.valid_from")}
            </label>
            <input id="field-valid_from" type="date" className={ui.input} value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
          </div>
          <div>
            <label htmlFor="field-evidence" className={ui.label}>
              {t("fields.evidence")}
            </label>
            <input
              id="field-evidence"
              type="file"
              accept="application/pdf,image/jpeg,image/png,image/heic"
              className={ui.input}
              onChange={(e) => setEvidence(e.target.files?.[0] ?? null)}
            />
          </div>
        </>
      ) : null}
      <p className={ui.help}>{tPortal("proposalNotice")}</p>
      <div className={ui.formActions}>
        <button type="submit" className={`${ui.primary} ${ui.actionFull}`} disabled={busy}>
          {t("submit")}
        </button>
      </div>
    </form>
  );
}
