"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { API } from "@/lib/immoware";
import { ui } from "@/lib/ui";

type StoredAssignment = {
  id: string;
  report_type: string;
  header: string;
  target_field: string | null;
  use_count: number;
  last_used_at: string | null;
};

/** Remembered column assignments of the tenant with removal (AE37, GAE-36). Removing one only
 *  makes the header heuristic propose it freshly; nothing is imported or changed. */
export function ColumnAssignments() {
  const t = useTranslations("Immoware24");
  const [items, setItems] = useState<StoredAssignment[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void bff<StoredAssignment[]>(`${API}/column-assignments`).then((res) => {
      if (!active) return;
      if (res.ok && Array.isArray(res.data)) setItems(res.data);
      else if (!res.ok) setError(res.message);
    });
    return () => {
      active = false;
    };
  }, []);

  async function remove(item: StoredAssignment) {
    if (!window.confirm(t("assignments.confirm", { header: item.header }))) return;
    setBusy(item.id);
    setError(null);
    const res = await bff<unknown>(`${API}/column-assignments/${item.id}`, { method: "DELETE" });
    setBusy(null);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setItems((prev) => (prev ? prev.filter((x) => x.id !== item.id) : prev));
  }

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="column-assignments-title">
      <h2 id="column-assignments-title" className="text-sm font-semibold">
        {t("assignments.title")}
      </h2>
      <p className="text-sm text-muted">{t("assignments.intro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {items && items.length === 0 ? <p className="text-sm text-muted">{t("assignments.empty")}</p> : null}
      {items && items.length > 0 ? (
        <div className={ui.tableScroll}>
          <table className={ui.table} data-testid="column-assignments">
            <thead>
              <tr>
                <th>{t("detect.colReport")}</th>
                <th>{t("assignments.colHeader")}</th>
                <th>{t("assignments.colTarget")}</th>
                <th>{t("assignments.colUses")}</th>
                <th>{t("assignments.colLastUsed")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>{t(`report.${item.report_type}`)}</td>
                  <td>{item.header}</td>
                  <td>{item.target_field ?? t("assignments.ignored")}</td>
                  <td className={ui.num}>{item.use_count}</td>
                  <td>{formatDateTime(item.last_used_at)}</td>
                  <td>
                    <button
                      type="button"
                      className={ui.buttonSm}
                      disabled={busy === item.id}
                      onClick={() => void remove(item)}
                    >
                      {t("assignments.remove")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
