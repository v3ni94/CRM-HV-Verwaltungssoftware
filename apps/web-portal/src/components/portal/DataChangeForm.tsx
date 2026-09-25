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
 *  Verwaltung prüft und übernimmt die Änderung. */
export function DataChangeForm() {
  const t = useTranslations("DataChange");
  const tPortal = useTranslations("Portal");
  const [kind, setKind] = useState<Kind>("address");
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

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
    setBusy(true);
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
      <p className={ui.help}>{tPortal("proposalNotice")}</p>
      <div className={ui.formActions}>
        <button type="submit" className={`${ui.primary} ${ui.actionFull}`} disabled={busy}>
          {t("submit")}
        </button>
      </div>
    </form>
  );
}
