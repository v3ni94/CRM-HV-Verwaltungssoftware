"use client";
/** Quelle und Bestätigung je Umlageschlüssel (GAM-108, AP17): Art der Quelle (Teilungserklärung,
 *  Vereinbarung, Beschluss), Fundstelle und Geltungsbeginn erfassen (PATCH allocation-keys/{id}),
 *  bestätigen oder Bestätigung aufheben (PUT .../confirmation). Die Bestätigung belegt die
 *  Prüfung der Quelle, nicht die Wirksamkeit des Schlüssels (M17-01 bleibt offen). */
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export const SOURCE_KINDS = ["declaration_of_division", "agreement", "resolution"] as const;

export type KeySource = {
  id: string;
  code: string;
  name: string;
  is_template_derived: boolean;
  source_kind: string | null;
  source_reference: string | null;
  source_document_id: string | null;
  source_valid_from: string | null;
  confirmed_at: string | null;
};
type Draft = { source_kind: string; source_reference: string; source_valid_from: string };

const draftOf = (k: KeySource): Draft => ({
  source_kind: k.source_kind ?? "",
  source_reference: k.source_reference ?? "",
  source_valid_from: k.source_valid_from ?? "",
});

/** Confirmation needs kind, start of validity and a reference or a document (API checks too). */
export function canConfirm(k: KeySource): boolean {
  return Boolean(k.source_kind && k.source_valid_from && (k.source_reference || k.source_document_id));
}

export function AllocationKeySources({ propertyId, canEdit }: { propertyId: string; canEdit: boolean }) {
  const t = useTranslations("AllocationKeys.sources");
  const [keys, setKeys] = useState<KeySource[]>([]);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await bff<KeySource[]>(`/api/bff/properties/${propertyId}/allocation-keys`);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    const rows = Array.isArray(res.data) ? res.data : [];
    setKeys(rows);
    setDrafts(Object.fromEntries(rows.map((k) => [k.id, draftOf(k)])));
  }, [propertyId]);
  useEffect(() => {
    void load();
  }, [load]);

  const send = async (url: string, method: string, body: unknown) => {
    setBusy(true);
    setError(null);
    const res = await bff(url, { method, body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) setError(res.message);
    else await load();
  };
  const base = (k: KeySource) => `/api/bff/properties/${propertyId}/allocation-keys/${k.id}`;
  const saveSource = (k: KeySource) => {
    const d = drafts[k.id] ?? draftOf(k);
    return send(base(k), "PATCH", {
      source_kind: d.source_kind || null,
      source_reference: d.source_reference.trim() || null,
      source_valid_from: d.source_valid_from || null,
    });
  };
  const setDraft = (id: string, patch: Partial<Draft>) =>
    setDrafts((p) => ({ ...p, [id]: { ...(p[id] ?? { source_kind: "", source_reference: "", source_valid_from: "" }), ...patch } }));

  if (!keys.length) return null;
  return (
    <div className="mt-4" data-testid="allocation-key-sources">
      <h3 className={ui.subtitle}>{t("title")}</h3>
      <p className="mt-1 text-xs text-muted">{t("intro")}</p>
      <div className="mt-2 overflow-x-auto">
        <table className={ui.table}>
          <thead>
            <tr>
              <th>{t("key")}</th>
              <th>{t("kind")}</th>
              <th>{t("reference")}</th>
              <th>{t("validFrom")}</th>
              <th>{t("status")}</th>
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => {
              const d = drafts[k.id] ?? draftOf(k);
              const dirty = JSON.stringify(d) !== JSON.stringify(draftOf(k));
              return (
                <tr key={k.id}>
                  <td>
                    <span className="font-medium">{k.code}</span>{" "}
                    {k.is_template_derived ? <span className={ui.badgeWarning}>{t("templateDerived")}</span> : null}
                  </td>
                  <td>
                    <select
                      aria-label={t("kindFor", { code: k.code })}
                      className={ui.input}
                      value={d.source_kind}
                      disabled={!canEdit}
                      onChange={(e) => setDraft(k.id, { source_kind: e.target.value })}
                    >
                      <option value="">{t("none")}</option>
                      {SOURCE_KINDS.map((s) => (
                        <option key={s} value={s}>
                          {t(`kinds.${s}`)}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <input
                      aria-label={t("referenceFor", { code: k.code })}
                      className={ui.input}
                      value={d.source_reference}
                      maxLength={500}
                      disabled={!canEdit}
                      onChange={(e) => setDraft(k.id, { source_reference: e.target.value })}
                    />
                  </td>
                  <td>
                    <input
                      type="date"
                      aria-label={t("validFromFor", { code: k.code })}
                      className={ui.input}
                      value={d.source_valid_from}
                      disabled={!canEdit}
                      onChange={(e) => setDraft(k.id, { source_valid_from: e.target.value })}
                    />
                  </td>
                  <td>
                    <div className="flex flex-col gap-1">
                      {k.confirmed_at ? (
                        <span className={ui.badgeSuccess}>{t("confirmedAt", { at: formatDateTime(k.confirmed_at) })}</span>
                      ) : (
                        <span className="text-muted">{t("unconfirmed")}</span>
                      )}
                      {k.source_valid_from && !dirty ? <span className="text-xs text-muted">{t("since", { date: formatDate(k.source_valid_from) })}</span> : null}
                      {canEdit ? (
                        <span className="flex flex-wrap gap-1">
                          {dirty ? (
                            <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void saveSource(k)}>
                              {t("save")}
                            </button>
                          ) : k.confirmed_at ? (
                            <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void send(`${base(k)}/confirmation`, "PUT", { confirmed: false })}>
                              {t("unconfirm")}
                            </button>
                          ) : (
                            <button
                              type="button"
                              className={ui.buttonSm}
                              disabled={busy || !canConfirm(k)}
                              onClick={() => void send(`${base(k)}/confirmation`, "PUT", { confirmed: true })}
                            >
                              {t("confirm", { code: k.code })}
                            </button>
                          )}
                        </span>
                      ) : null}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-xs text-muted">{t("hint")}</p>
      {error ? (
        <p role="alert" className={`${ui.alert} mt-2`}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
