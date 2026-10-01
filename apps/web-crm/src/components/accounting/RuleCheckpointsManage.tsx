"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export type Checkpoint = {
  id: string;
  title: string;
  effective_from: string;
  source_status: string;
  change_reason: string;
  state: "open" | "upcoming" | "due" | "done" | "withdrawn";
  days_until: number;
};

/** AB10-01: maintain dated check points (date, title, source). Hint only, no legal effect. */
export function RuleCheckpointsManage() {
  const t = useTranslations("Accounting.ruleCheckpointsManage");
  const [rows, setRows] = useState<Checkpoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [date, setDate] = useState("");
  const [name, setName] = useState("");
  const [source, setSource] = useState("");
  const [note, setNote] = useState("");
  const base = "/api/bff/accounting/rule-versions/checkpoints";
  const load = useCallback(async () => {
    const res = await bff<Checkpoint[]>(base);
    if (res.ok) setRows(res.data ?? []);
    else setError(res.message);
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  async function add() {
    setError(null);
    const res = await bff<Checkpoint>(base, {
      method: "POST",
      body: JSON.stringify({ title: name, effective_from: date, source, note }),
    });
    if (!res.ok) return setError(res.message);
    setName("");
    setSource("");
    setNote("");
    await load();
  }
  async function withdraw(id: string) {
    const res = await bff(`/api/bff/accounting/rule-versions/${id}/withdraw`, { method: "POST" });
    if (!res.ok) return setError(res.message);
    await load();
  }
  return (
    <section className="flex flex-col gap-2" data-testid="rule-checkpoints-manage">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className={ui.notice}>{t("notice")}</p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          {t("date")}
          <input className={ui.input} type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          {t("name")}
          <input className={ui.input} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          {t("source")}
          <input className={ui.input} value={source} onChange={(e) => setSource(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          {t("note")}
          <input className={ui.input} value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        <button type="button" className={ui.secondary} disabled={!date || !name} onClick={() => void add()}>
          {t("add")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {rows === null ? null : rows.length === 0 ? (
        <EmptyState title={t("empty")} />
      ) : (
        <div className="overflow-x-auto">
          <table className="mhvp-table">
            <thead>
              <tr>
                <th>{t("date")}</th>
                <th>{t("name")}</th>
                <th>{t("source")}</th>
                <th>{t("state")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{formatDate(r.effective_from)}</td>
                  <td>{r.title}</td>
                  <td>{r.source_status}</td>
                  <td>{t(`states.${r.state}`)}</td>
                  <td>
                    {r.state === "withdrawn" || r.state === "done" ? null : (
                      <button type="button" className={ui.secondary} onClick={() => void withdraw(r.id)}>
                        {t("withdraw")}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
