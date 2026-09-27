"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { bff } from "@/lib/bff";
import { fieldPath } from "@/lib/problem";
import { ui } from "@/lib/ui";

type Kind = "address" | "phone" | "email" | "bank_account";
const KINDS: Kind[] = ["address", "phone", "email", "bank_account"];

const FIELDS: Record<Kind, string[]> = {
  address: ["street", "house_number", "postal_code", "city"],
  phone: ["number"],
  email: ["email"],
  bank_account: ["iban"],
};

/** Passende Eingabetypen und Autofill-Hinweise je Feld (Tastatur auf Mobilgeräten, Autofill). */
const INPUT_ATTRIBUTES: Record<string, { type?: string; autoComplete?: string; inputMode?: "numeric" }> = {
  street: { autoComplete: "address-line1" },
  postal_code: { autoComplete: "postal-code", inputMode: "numeric" },
  city: { autoComplete: "address-level2" },
  number: { type: "tel", autoComplete: "tel" },
  email: { type: "email", autoComplete: "email" },
};

/** Datenänderung (M21): Anschrift, Telefon, E-Mail oder Bankverbindung als Vorschlag; die
 *  Verwaltung prüft und übernimmt die Änderung. */
export function DataChangeForm() {
  const t = useTranslations("DataChange");
  const tPortal = useTranslations("Portal");
  const [kind, setKind] = useState<Kind>("address");
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const doneRef = useRef<HTMLParagraphElement>(null);

  // Keyboard/Screenreader: after a successful submit the focus moves to the confirmation
  // (same pattern as the heading focus in PortalForms).
  useEffect(() => {
    if (done) doneRef.current?.focus();
  }, [done]);

  function setField(name: string, v: string) {
    setValues((prev) => ({ ...prev, [name]: v }));
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setFieldErrors({});
    setDone(false);
    const payload: Record<string, string> = {};
    for (const name of FIELDS[kind]) payload[name] = (values[name] ?? "").trim();
    if (Object.values(payload).every((v) => !v)) {
      setError(t("required"));
      return;
    }
    setBusy(true);
    const result = await bff<{ id: string }>("/api/bff/portal/change-requests", {
      method: "POST",
      body: JSON.stringify({ kind, payload }),
    });
    setBusy(false);
    if (!result.ok) {
      // 422: Feldfehler der API (z. B. ["body", "payload", "email"]) den Eingabefeldern zuordnen.
      const errors: Record<string, string> = {};
      for (const fieldError of result.status === 422 ? (result.problem?.errors ?? []) : []) {
        const name = fieldPath(fieldError.location)?.split(".").pop();
        if (name && FIELDS[kind].includes(name)) errors[name] = fieldError.message;
      }
      setFieldErrors(errors);
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
      {done ? (
        <p ref={doneRef} tabIndex={-1} role="status" className={`${ui.success} focus:outline-none`}>
          {t("submitted")}
        </p>
      ) : null}
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
            setFieldErrors({});
          }}
        >
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {t(`kindOptions.${k}`)}
            </option>
          ))}
        </select>
      </div>
      {FIELDS[kind].map((name) => {
        const attributes = INPUT_ATTRIBUTES[name] ?? {};
        const fieldError = fieldErrors[name];
        return (
          <div key={name}>
            <label htmlFor={`field-${name}`} className={ui.label}>
              {t(`fields.${name}`)}
            </label>
            <input
              id={`field-${name}`}
              type={attributes.type ?? "text"}
              autoComplete={attributes.autoComplete}
              inputMode={attributes.inputMode}
              className={ui.input}
              value={values[name] ?? ""}
              aria-invalid={fieldError ? true : undefined}
              aria-describedby={fieldError ? `field-${name}-error` : undefined}
              onChange={(e) => setField(name, e.target.value)}
            />
            {fieldError ? (
              <p id={`field-${name}-error`} className={ui.error}>
                {fieldError}
              </p>
            ) : null}
          </div>
        );
      })}
      <p className={ui.help}>{tPortal("proposalNotice")}</p>
      <div className={ui.formActions}>
        <button type="submit" className={`${ui.primary} ${ui.actionFull}`} disabled={busy}>
          {t("submit")}
        </button>
      </div>
    </form>
  );
}
