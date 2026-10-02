"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";
import { useBusy } from "@/lib/use-busy";

/** AE10 (AA07-01): tenant rule per acquisition kind. Default is manual release; the legal
 *  question per kind is open, the screen only configures the proposed debtor of drafts. */

type Rule = { acquisition_kind: string; kind_label: string; variant: string; is_default: boolean; source_note: string | null };
type Payload = { items: Rule[]; variants: { code: string; label: string }[]; note: string };

export function AcquisitionRules() {
  const { busy, guard } = useBusy();
  const t = useTranslations("HoaAcquisitionRule");
  const tCommon = useTranslations("Common");
  const [data, setData] = useState<Payload | null>(null);
  const [edits, setEdits] = useState<Record<string, { variant?: string; source_note?: string }>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void bff<Payload>("/api/bff/hoa/acquisition-rules").then((res) => {
      if (res.ok) setData(res.data);
      else setError(t("loadFailed"));
    });
  }, [t]);

  const save = async (rule: Rule) => {
    const edit = edits[rule.acquisition_kind] ?? {};
    setError(null);
    setMessage(null);
    const res = await bff<Rule>(`/api/bff/hoa/acquisition-rules/${rule.acquisition_kind}`, {
      method: "PUT",
      body: JSON.stringify({ variant: edit.variant ?? rule.variant, source_note: (edit.source_note ?? rule.source_note ?? "") || null }),
    });
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setData((d) => (d ? { ...d, items: d.items.map((i) => (i.acquisition_kind === rule.acquisition_kind ? res.data : i)) } : d));
    setEdits((e) => ({ ...e, [rule.acquisition_kind]: {} }));
    setMessage(t("saved"));
  };

  return (
    <section className={ui.card} data-testid="acquisition-rules">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className="mt-1 text-sm text-muted">{t("intro")}</p>
      {data ? <p className="text-xs text-subtle">{data.note}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {message ? <p role="status">{message}</p> : null}
      <ul className="mt-2 flex flex-col gap-3">
        {(data?.items ?? []).length === 0 ? <li className="text-sm text-muted">{tCommon("emptyList")}</li> : null}
        {(data?.items ?? []).map((rule) => (
          <li key={rule.acquisition_kind} className="flex flex-wrap items-end gap-2 rounded border border-border p-3">
            <span className="min-w-40 font-medium">{rule.kind_label}</span>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("variant")}</span>
              <select
                className={ui.input}
                aria-label={`${t("variant")} ${rule.kind_label}`}
                value={edits[rule.acquisition_kind]?.variant ?? rule.variant}
                onChange={(e) => setEdits({ ...edits, [rule.acquisition_kind]: { ...edits[rule.acquisition_kind], variant: e.target.value } })}
              >
                {data?.variants.map((v) => (
                  <option key={v.code} value={v.code}>
                    {v.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("sourceNote")}</span>
              <input
                className={ui.input}
                value={edits[rule.acquisition_kind]?.source_note ?? rule.source_note ?? ""}
                onChange={(e) => setEdits({ ...edits, [rule.acquisition_kind]: { ...edits[rule.acquisition_kind], source_note: e.target.value } })}
              />
            </label>
            <button disabled={busy} type="button" className={ui.secondary} onClick={guard(() => save(rule))}>
              {t("save")}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
