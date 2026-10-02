"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";
import { useBusy } from "@/lib/use-busy";

export type RequiredDocument = { id: string; management_type: string; document_category_id: string; mandatory: boolean };
type Category = { id: string; code: string; name: string };
const TYPES = ["rental", "hoa", "hoa_with_sev"] as const;

/** Pflichtunterlagen je Verwaltungsart (M35, Vollständigkeitsprüfung der Objektakte) und Stand des
 *  lokalen Klassifikationsmodells mit Vorschlag je Prüffall. Das Modell schlägt nur vor. */
export function RequiredDocuments({ categories, canManage, canDelete }: { categories: Category[]; canManage: boolean; canDelete: boolean }) {
  const { busy, guard } = useBusy();
  const t = useTranslations("ObjektakteRequired");
  const [rows, setRows] = useState<RequiredDocument[]>([]);
  const [type, setType] = useState<string>(TYPES[0]);
  const [category, setCategory] = useState("");
  const [mandatory, setMandatory] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await bff<RequiredDocument[]>("/api/bff/objektakte/required-documents");
    if (res.ok) setRows(res.data);
    else setError(res.message);
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const name = (id: string) => categories.find((c) => c.id === id)?.name ?? id;
  const save = async () => {
    setError(null);
    const res = await bff("/api/bff/objektakte/required-documents", {
      method: "POST",
      body: JSON.stringify({ management_type: type, document_category_id: category, mandatory }),
    });
    if (!res.ok) return setError(res.message);
    await load();
  };
  const remove = async (id: string) => {
    const res = await bff(`/api/bff/objektakte/required-documents/${id}`, { method: "DELETE" });
    if (!res.ok) return setError(res.message);
    await load();
  };

  return (
    <section className={ui.card} aria-label={t("title")}>
      <h2 className="text-sm font-semibold">{t("title")}</h2>
      <p className={ui.help}>{t("intro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <ul className="mt-2 flex flex-col gap-1">
        {rows.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center gap-2 text-sm" data-testid="required-document">
            <span className={ui.badge}>{t(`type.${r.management_type}`)}</span>
            <span>{name(r.document_category_id)}</span>
            <span className={r.mandatory ? ui.badgeWarning : ui.badge}>{r.mandatory ? t("mandatory") : t("optional")}</span>
            {canDelete ? (
              <button disabled={busy} type="button" className={ui.buttonSm} onClick={guard(() => remove(r.id))}>
                {t("remove")}
              </button>
            ) : null}
          </li>
        ))}
        {rows.length === 0 ? <li className={ui.help}>{t("empty")}</li> : null}
      </ul>
      {canManage ? (
        <form
          className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("managementType")}</span>
            <select className={ui.input} value={type} onChange={(e) => setType(e.target.value)}>
              {TYPES.map((x) => (
                <option key={x} value={x}>
                  {t(`type.${x}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-1 flex-col gap-1">
            <span className={ui.label}>{t("category")}</span>
            <select className={ui.input} value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">{t("chooseCategory")}</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={mandatory} onChange={(e) => setMandatory(e.target.checked)} />
            {t("mandatory")}
          </label>
          <button type="submit" className={ui.buttonSm} disabled={!category}>
            {t("save")}
          </button>
        </form>
      ) : null}
    </section>
  );
}
