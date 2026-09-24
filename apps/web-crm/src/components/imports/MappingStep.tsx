"use client";

import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import { bff } from "@/lib/bff";
import {
  API,
  cleanMapping,
  distinctValues,
  missingRequired,
  type ImportField,
  type ImportMapping,
  type ImportSource,
  type StagingRow,
} from "@/lib/immoware";
import { ui } from "@/lib/ui";

type Props = {
  source: ImportSource;
  fields: ImportField[];
  mappings: ImportMapping[];
  onMapping: (mapping: ImportMapping) => void;
};

/** Step 3: assign file headers to target fields, value maps for choice fields, template versions. */
export function MappingStep({ source, fields, mappings, onMapping }: Props) {
  const t = useTranslations("Immoware24");
  const templates = mappings.filter((m) => m.report_type === source.report_type);
  const [columns, setColumns] = useState<Record<string, string>>({});
  const [valueMaps, setValueMaps] = useState<Record<string, Record<string, string>>>({});
  const [name, setName] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [rows, setRows] = useState<StagingRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    void bff<StagingRow[]>(`${API}/files/${source.id}/rows?limit=200`).then((res) => {
      if (active && res.ok) setRows(res.data);
    });
    return () => {
      active = false;
    };
  }, [source.id]);

  const missing = missingRequired(fields, columns);
  const choiceFields = useMemo(() => fields.filter((f) => f.choices.length> 0 && columns[f.name]), [fields, columns]);

  const pickTemplate = (id: string) => {
    setTemplateId(id);
    const tpl = templates.find((m) => m.id === id);
    if (!tpl) return;
    // Only headers present in this file are taken over.
    setColumns(Object.fromEntries(Object.entries(tpl.columns).filter(([, h]) => source.headers.includes(h))));
    setValueMaps(tpl.value_maps);
    setName(tpl.name);
  };

  const setColumn = (field: string, header: string) => {
    setTemplateId("");
    setColumns((c) => ({ ...c, [field]: header }));
  };
  const setValue = (field: string, from: string, to: string) => {
    setTemplateId("");
    setValueMaps((m) => ({ ...m, [field]: { ...(m[field] ?? {}), [from]: to } }));
  };

  const save = async () => {
    setError(null);
    if (missing.length) return setError(t("requiredMissing", { fields: missing.map((f) => f.label).join(", ") }));
    if (!name.trim()) return setError(t("templateNameRequired"));
    setBusy(true);
    const res = await bff<ImportMapping>(`${API}/mappings`, {
      method: "POST",
      body: JSON.stringify({ report_type: source.report_type, name: name.trim(), ...cleanMapping(columns, valueMaps) }),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    onMapping(res.data);
  };

  const useTemplate = () => {
    const tpl = templates.find((m) => m.id === templateId);
    if (tpl) onMapping(tpl);
  };

  return (
    <section className="flex flex-col gap-4" aria-labelledby="mapping-title">
      <h2 id="mapping-title" className={ui.h2}>
        {t("mappingTitle")}
      </h2>
      {templates.length> 0 ? (
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("template")}</span>
            <select className={ui.input} value={templateId} onChange={(e) => pickTemplate(e.target.value)}>
              <option value="">{t("templateNone")}</option>
              {templates.map((m) => (
                <option key={m.id} value={m.id}>
                  {t("templateOption", { name: m.name, version: m.version })}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className={ui.button} disabled={!templateId || missing.length> 0} onClick={useTemplate}>
            {t("templateUse")}
          </button>
        </div>
      ) : null}

      {fields.length === 0 ? (
        <p className={ui.notice}>{t("stagedOnlyMapping")}</p>
      ) : (
        <div className="overflow-x-auto">
<table className="mhvp-table">
          <thead>
            <tr>
              <th>{t("colTarget")}</th>
              <th>{t("colSourceHeader")}</th>
            </tr>
          </thead>
          <tbody>
            {fields.map((f) => (
              <tr key={f.name}>
                <td>
                  <label htmlFor={`col-${f.name}`}>
                    {f.label}
                    {f.required ? <span className="ml-1 text-danger-fg">{t("requiredMark")}</span> : null}
                  </label>
                </td>
                <td>
                  <select
                    id={`col-${f.name}`}
                    className={ui.input}
                    value={columns[f.name] ?? ""}
                    aria-required={f.required}
                    onChange={(e) => setColumn(f.name, e.target.value)}
>
                    <option value="">{t("notAssigned")}</option>
                    {source.headers.map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
</div>
      )}

      {choiceFields.map((f) => {
        const values = distinctValues(rows, columns[f.name]!);
        return (
          <fieldset key={f.name} className={ui.card} data-testid={`value-map-${f.name}`}>
            <legend className="px-1 text-sm font-medium">{t("valueMapTitle", { field: f.label })}</legend>
            {values.length === 0 ? (
              <p className="text-sm text-muted">{t("valueMapEmpty")}</p>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {values.map((v) => (
                  <label key={v} className="flex flex-col gap-1">
                    <span className={ui.label}>{v}</span>
                    <select className={ui.input} value={valueMaps[f.name]?.[v] ?? ""} onChange={(e) => setValue(f.name, v, e.target.value)}>
                      <option value="">{t("valueUnchanged")}</option>
                      {f.choices.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
            )}
          </fieldset>
        );
      })}

      {missing.length> 0 ? (
        <p className="text-sm text-muted" data-testid="required-missing">
          {t("requiredMissing", { fields: missing.map((f) => f.label).join(", ") })}
        </p>
      ) : null}
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("templateName")}</span>
          <input className={ui.input} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <button type="button" className={ui.primary} disabled={busy || missing.length> 0} onClick={save}>
          {t("templateSave")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
