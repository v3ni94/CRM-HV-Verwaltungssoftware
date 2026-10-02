"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type DisruptionRow = {
  id: string;
  resolved: boolean;
  description: string;
  occurred_at: string;
  affected_contract_ids?: string[];
};

/** GAF-15: Störungsprotokoll der Online-Versammlung (D53). Einträge werden nie gelöscht. */
export function MeetingDisruptions({ meetingId, rows, closed }: { meetingId: string; rows: DisruptionRow[]; closed: boolean }) {
  const t = useTranslations("HoaAF09.disruptions");
  const router = useRouter();
  const [description, setDescription] = useState("");
  const [occurredAt, setOccurredAt] = useState("");
  const [resolved, setResolved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async () => {
    setError(null);
    if (!description.trim() || !occurredAt) {
      setError(t("required"));
      return;
    }
    setBusy(true);
    const res = await bff(`/api/bff/hoa/meetings/${meetingId}/disruptions`, {
      method: "POST",
      body: JSON.stringify({ description: description.trim(), occurred_at: new Date(occurredAt).toISOString(), resolved }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setDescription("");
    setResolved(false);
    router.refresh();
  };
  return (
    <section className="flex flex-col gap-2" data-testid="meeting-disruptions">
      <h2 className="text-base font-semibold">{t("title")}</h2>
      <p className="text-sm text-muted">{t("hint")}</p>
      {rows.length === 0 ? <p className="text-sm text-muted">{t("none")}</p> : null}
      <ul className="flex flex-col gap-1 text-sm">
        {rows.map((r) => (
          <li key={r.id}>
            {formatDateTime(r.occurred_at)} · {t(r.resolved ? "resolved" : "open")} · {r.description}
            {r.affected_contract_ids?.length ? ` · ${t("affected", { n: r.affected_contract_ids.length })}` : ""}
          </li>
        ))}
      </ul>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {closed ? null : (
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("description")}</span>
            <input className={ui.input} value={description} onChange={(e) => setDescription(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("occurredAt")}</span>
            <input type="datetime-local" className={ui.input} value={occurredAt} onChange={(e) => setOccurredAt(e.target.value)} />
          </label>
          <label className="flex items-center gap-1 text-sm">
            <input type="checkbox" checked={resolved} onChange={(e) => setResolved(e.target.checked)} />
            {t("resolvedCheck")}
          </label>
          <button type="button" className={ui.secondary} disabled={busy} onClick={() => void submit()}>
            {t("save")}
          </button>
        </div>
      )}
    </section>
  );
}
