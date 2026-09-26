"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export const SUBJECT_KINDS = [
  "economic_plan",
  "annual_statement",
  "maintenance",
  "structural_change",
  "manager_appointment",
  "other",
] as const;
const MAJORITY_TYPES = ["simple", "qualified_2_3", "qualified_3_4", "unanimous", "custom"] as const;
const BASES = ["heads", "shares", "units"] as const;

export type SubjectRule = {
  id: string;
  legal_entity_id: string | null;
  subject_kind: string;
  majority_type: string;
  custom_numerator: number | null;
  custom_denominator: number | null;
  counting_basis: string;
  source: string;
  approved_by: string | null;
  rule_text: string;
};

export type HoaEntity = { id: string; name: string };

const EMPTY = {
  legal_entity_id: "",
  subject_kind: "economic_plan",
  majority_type: "simple",
  custom_numerator: "",
  custom_denominator: "",
  counting_basis: "heads",
  source: "",
};

/** Mehrheitsregeln je Beschlussgegenstand (M25-01): Mandantenregel mit optionalem Override je
 *  GdWE, Fundstelle Pflicht, fachliche Freigabe durch eine zweite Person. Die Auswertung ist nur
 *  Anzeige; die Verkündung bleibt bei der Versammlungsleitung. */
export function MajorityRulesAdmin({
  rules,
  entities,
  canManage,
}: {
  rules: SubjectRule[];
  entities: HoaEntity[];
  canManage: boolean;
}) {
  const t = useTranslations("MajorityRules");
  const router = useRouter();
  const [form, setForm] = useState(EMPTY);
  const [editId, setEditId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const entityName = (id: string | null) => (id ? (entities.find((e) => e.id === id)?.name ?? id) : t("tenantWide"));

  const send = async (path: string, method: string, body?: unknown) => {
    setBusy(true);
    setError(null);
    setSaved(false);
    const res = await bff(`/api/bff/hoa/majority-rules/subject-rules${path}`, {
      method,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return false;
    }
    setSaved(true);
    router.refresh();
    return true;
  };
  const custom = form.majority_type === "custom";
  const num = Number(form.custom_numerator);
  const den = Number(form.custom_denominator);
  const customValid = !custom || (Number.isInteger(num) && Number.isInteger(den) && num > 0 && den > 0 && num <= den);
  const sourceValid = form.source.trim().length >= 3;
  const hint = !sourceValid ? t("sourceRequired") : !customValid ? t("customInvalid") : null;

  const save = async () => {
    const body = {
      legal_entity_id: form.legal_entity_id || null,
      subject_kind: form.subject_kind,
      majority_type: form.majority_type,
      custom_numerator: custom ? Number(form.custom_numerator) : null,
      custom_denominator: custom ? Number(form.custom_denominator) : null,
      counting_basis: form.counting_basis,
      source: form.source,
    };
    const ok = editId ? await send(`/${editId}`, "PUT", body) : await send("", "POST", body);
    if (ok) {
      setForm(EMPTY);
      setEditId(null);
    }
  };

  const edit = (r: SubjectRule) => {
    setEditId(r.id);
    setForm({
      legal_entity_id: r.legal_entity_id ?? "",
      subject_kind: r.subject_kind,
      majority_type: r.majority_type,
      custom_numerator: r.custom_numerator ? String(r.custom_numerator) : "",
      custom_denominator: r.custom_denominator ? String(r.custom_denominator) : "",
      counting_basis: r.counting_basis,
      source: r.source,
    });
  };

  const set = (key: keyof typeof EMPTY) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }));

  return (
    <div className="flex flex-col gap-4">
      <p className={ui.notice}>{t("notice")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {saved ? (
        <p role="status" className={ui.success}>
          {t("saved")}
        </p>
      ) : null}
      {rules.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("subjectKind")}</th>
                <th>{t("scope")}</th>
                <th>{t("majorityType")}</th>
                <th>{t("countingBasis")}</th>
                <th>{t("source")}</th>
                <th>{t("approval")}</th>
                {canManage ? <th /> : null}
              </tr>
            </thead>
            <tbody>
              {rules.map((r) => (
                <tr key={r.id}>
                  <td>{t(`subjectKinds.${r.subject_kind}`)}</td>
                  <td>{entityName(r.legal_entity_id)}</td>
                  <td>
                    {r.majority_type === "custom"
                      ? t("customValue", { n: r.custom_numerator ?? 0, d: r.custom_denominator ?? 0 })
                      : t(`types.${r.majority_type}`)}
                  </td>
                  <td>{t(`bases.${r.counting_basis}`)}</td>
                  <td>{r.source}</td>
                  <td>
                    <span className={r.approved_by ? ui.badgeSuccess : ui.badgeWarning}>{t(r.approved_by ? "approved" : "notApproved")}</span>
                  </td>
                  {canManage ? (
                    <td className="whitespace-nowrap">
                      <button type="button" className={ui.buttonSm} onClick={() => edit(r)} disabled={busy}>
                        {t("edit")}
                      </button>
                      {!r.approved_by ? (
                        <button type="button" className={ui.buttonSm} onClick={() => send(`/${r.id}/approve`, "POST")} disabled={busy}>
                          {t("approve")}
                        </button>
                      ) : null}
                      <button
                        type="button"
                        className={ui.buttonSm}
                        onClick={() => window.confirm(t("confirmDelete")) && send(`/${r.id}`, "DELETE")}
                        disabled={busy}
                      >
                        {t("delete")}
                      </button>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {canManage ? (
        <div className={ui.card}>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("subjectKind")}</span>
              <select className={ui.input} value={form.subject_kind} onChange={set("subject_kind")}>
                {SUBJECT_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {t(`subjectKinds.${k}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("scope")}</span>
              <select className={ui.input} value={form.legal_entity_id} onChange={set("legal_entity_id")}>
                <option value="">{t("tenantWide")}</option>
                {entities.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("majorityType")}</span>
              <select className={ui.input} value={form.majority_type} onChange={set("majority_type")}>
                {MAJORITY_TYPES.map((k) => (
                  <option key={k} value={k}>
                    {t(`types.${k}`)}
                  </option>
                ))}
              </select>
            </label>
            {form.majority_type === "custom" ? (
              <>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("numerator")}</span>
                  <input type="number" min={1} className={ui.input} value={form.custom_numerator} onChange={set("custom_numerator")} />
                </label>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("denominator")}</span>
                  <input type="number" min={1} className={ui.input} value={form.custom_denominator} onChange={set("custom_denominator")} />
                </label>
              </>
            ) : null}
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("countingBasis")}</span>
              <select className={ui.input} value={form.counting_basis} onChange={set("counting_basis")}>
                {BASES.map((k) => (
                  <option key={k} value={k}>
                    {t(`bases.${k}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex min-w-64 flex-1 flex-col gap-1">
              <span className={ui.label}>{t("source")}</span>
              <input className={ui.input} value={form.source} placeholder={t("sourcePlaceholder")} onChange={set("source")} />
            </label>
            <button type="button" className={ui.primary} onClick={save} disabled={busy || !sourceValid || !customValid}>
              {t(editId ? "update" : "create")}
            </button>
            {editId ? (
              <button type="button" className={ui.button} onClick={() => (setEditId(null), setForm(EMPTY))}>
                {t("cancel")}
              </button>
            ) : null}
          </div>
          {hint ? <p className={`${ui.help} mt-2`}>{hint}</p> : null}
        </div>
      ) : null}
    </div>
  );
}
