"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type ExportKind = { kind: string; label: string; columns: string[]; required: string[]; reconciled: boolean };

/** Bekannte Immoware24-Exporttypen mit erwarteten Spalten (Pflichtspalten markiert). */
export function ExportKinds() {
  const t = useTranslations("ExportKinds");
  const tCommon = useTranslations("Common");
  const [kinds, setKinds] = useState<ExportKind[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    void bff<ExportKind[]>("/api/bff/imports/immoware24/vollimport/exporttypen").then((r) => (r.ok ? setKinds(r.data) : setError(r.message)));
  }, []);
  return (
    <details className={ui.card} data-testid="export-kinds">
      <summary className="cursor-pointer text-sm font-semibold">{t("title")}</summary>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <ul className="mt-2 flex flex-col gap-2 text-sm">
        {(kinds ?? []).length === 0 ? <li className="text-sm text-muted">{tCommon("emptyList")}</li> : null}
        {(kinds ?? []).map((k) => (
          <li key={k.kind}>
            <span className="font-medium">{k.label}</span> <span className={ui.help}>({k.kind}{k.reconciled ? `, ${t("reconciled")}` : ""})</span>
            <p className={ui.help}>{k.columns.map((c) => (k.required.includes(c) ? `${c} *` : c)).join(", ")}</p>
          </li>
        ))}
      </ul>
    </details>
  );
}
