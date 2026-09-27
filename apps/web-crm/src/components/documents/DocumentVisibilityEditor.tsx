"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

const ROLES = ["owner", "tenant", "provider", "board"] as const;

/** Freigabeflag je Dokument (M21-03): intern (kein Portal), Eigentümer, Mieter, Dienstleister,
 *  Beirat. "intern" wird als explizite Wahl gespeichert (visibility = ["internal"]), damit ein
 *  Dokument nie versehentlich ohne Entscheidung sichtbar wird. */
export function DocumentVisibilityEditor({ documentId, visibility, canEdit }: { documentId: string; visibility: string[]; canEdit: boolean }) {
  const t = useTranslations("DocumentDetail");
  const [roles, setRoles] = useState<string[]>(visibility.filter((v) => v !== "internal"));
  const [saved, setSaved] = useState<string[]>(visibility);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const label = (values: string[]) =>
    values.filter((v) => v !== "internal").length
      ? values.filter((v) => v !== "internal").map((v) => t(`visibilityValues.${v}`)).join(", ")
      : t("visibilityValues.internal");

  async function save() {
    setBusy(true);
    setError(null);
    const next = roles.length ? roles : ["internal"];
    const result = await bff(`/api/bff/documents/${documentId}`, { method: "PATCH", body: JSON.stringify({ visibility: next }) });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setSaved(next);
  }

  if (!canEdit) return <p className="mt-1 text-sm">{label(saved)}</p>;
  return (
    <div className="mt-1 flex flex-col gap-2 text-sm">
      <p data-testid="visibility-current">{label(saved)}</p>
      <fieldset className="flex flex-wrap gap-3">
        <legend className="sr-only">{t("visibility")}</legend>
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={roles.length === 0} onChange={() => setRoles([])} />
          {t("visibilityValues.internal")}
        </label>
        {ROLES.map((role) => (
          <label key={role} className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={roles.includes(role)}
              onChange={(e) => setRoles((prev) => (e.target.checked ? [...prev, role] : prev.filter((r) => r !== role)))}
            />
            {t(`visibilityValues.${role}`)}
          </label>
        ))}
      </fieldset>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div>
        <button type="button" className={ui.buttonSm} disabled={busy} onClick={save}>
          {t("visibilitySave")}
        </button>
      </div>
    </div>
  );
}
