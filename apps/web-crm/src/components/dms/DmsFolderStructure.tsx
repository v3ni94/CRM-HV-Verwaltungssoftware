"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Folder = {
  folder: string;
  description: string;
  per_unit_and_person: boolean;
  categories: { id: string; code: string; name: string }[];
  subfolders: { name: string; document_types: string[] }[];
  subfolders_source: string | null;
};

/** Standard folder structure of the property file (11.2) as GET /document-folders describes
 *  it (Package F, handbook Objektordner): the six folders with their filing rule, the
 *  categories that file there and, for 04 and 05, the subfolders known from the objektakte
 *  takeover. A tenant without the standard categories 04 and 05 can add them here
 *  (tenant_settings:update). */
export function DmsFolderStructure({ canEnsureDefaults = false }: { canEnsureDefaults?: boolean }) {
  const t = useTranslations("DmsSearch.folders");
  const [folders, setFolders] = useState<Folder[] | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  async function load() {
    const res = await bff<Folder[]>("/api/bff/document-folders");
    if (res.ok) setFolders(res.data);
    else setError(res.message);
  }

  useEffect(() => {
    void load();
  }, []);

  async function ensureDefaults() {
    setBusy(true);
    setError(null);
    setInfo(null);
    const res = await bff("/api/bff/document-categories/ensure-defaults", { method: "POST" });
    setBusy(false);
    if (res.ok) {
      setInfo(t("ensured"));
      await load();
    } else setError(res.message);
  }

  const missingStandard = folders?.some((f) => f.per_unit_and_person && f.categories.length === 0) ?? false;

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-label={t("title")} data-testid="dms-folder-structure">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className={ui.h2}>{t("title")}</h2>
        <button type="button" className={ui.buttonSm} onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          {open ? t("hide") : t("show")}
        </button>
      </div>
      <p className="text-sm text-muted">{t("intro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {info ? <p className={ui.success}>{info}</p> : null}
      {open && folders ? (
        <>
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("folder")}</th>
                <th>{t("content")}</th>
                <th>{t("categories")}</th>
                <th>{t("subfolders")}</th>
              </tr>
            </thead>
            <tbody>
              {folders.map((f) => (
                <tr key={f.folder}>
                  <td className="whitespace-nowrap font-medium">{f.folder}</td>
                  <td>{f.description}</td>
                  <td>{f.categories.length ? f.categories.map((c) => c.name).join(", ") : t("noCategory")}</td>
                  <td>
                    {f.per_unit_and_person ? (
                      f.subfolders.length ? (
                        <ul className="list-disc pl-4">
                          {f.subfolders.map((s) => (
                            <li key={s.name}>
                              {s.name}
                              {s.document_types.length ? <span className="text-muted"> ({s.document_types.join(", ")})</span> : null}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <span className="text-muted">{t("subfoldersUnknown")}</span>
                      )
                    ) : (
                      <span className="text-muted">{t("noSubfolders")}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className={ui.help}>{t("legalNote")}</p>
          {missingStandard ? (
            <div className="flex flex-wrap items-center gap-2">
              <p className={ui.notice}>{t("missingStandard")}</p>
              {canEnsureDefaults ? (
                <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void ensureDefaults()}>
                  {t("ensure")}
                </button>
              ) : null}
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
