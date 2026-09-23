"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type Prospect = { id: string; contact_id: string; status: string; delete_after: string; notes: string | null };
type Contact = { id: string; display_name: string };

const STATUSES = ["new", "viewing", "applied", "accepted", "rejected", "withdrawn"] as const;

/** Prospects per unit (M26) with a mandatory deletion date; personal data only as long as
 *  needed (M26-04). */
export function Prospects({ unitId, rows, names }: { unitId: string; rows: Prospect[]; names: Record<string, string> }) {
  const t = useTranslations("Prospects");
  const router = useRouter();
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Contact[]>([]);
  const [contact, setContact] = useState<Contact | null>(null);
  const [deleteAfter, setDeleteAfter] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const search = async () => {
    const res = await bff<{ items: Contact[] }>(`/api/bff/contacts?q=${encodeURIComponent(q.trim())}`);
    if (res.ok) setHits(res.data.items);
  };
  const run = async (path: string, method: string, body?: unknown) => {
    setBusy(true);
    setError(null);
    const res = await bff(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });
    setBusy(false);
    if (res.ok) router.refresh();
    else setError(res.message);
    return res.ok;
  };
  return (
    <section className="flex flex-col gap-2">
      <table className="w-full border-collapse text-sm">
        <tbody>
          {rows.map((p) => (
            <tr key={p.id} className="border-b border-border">
              <td className="py-1.5 pr-3">{names[p.contact_id] ?? p.contact_id}</td>
              <td className="py-1.5 pr-3">
                <select
                  aria-label={t("status")}
                  className={ui.input}
                  value={p.status}
                  disabled={busy}
                  onChange={(e) => run(`/api/bff/letting/prospects/${p.id}`, "PATCH", { status: e.target.value })}
                >
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {t(`statuses.${s}`)}
                    </option>
                  ))}
                </select>
              </td>
              <td className="py-1.5 pr-3 text-muted">{t("deleteAfter", { date: formatDate(p.delete_after) })}</td>
              <td className="py-1.5">
                <button
                  type="button"
                  className={ui.button}
                  disabled={busy}
                  onClick={() => window.confirm(t("confirmDelete")) && run(`/api/bff/letting/prospects/${p.id}`, "DELETE")}
                >
                  {t("delete")}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("searchContact")}</span>
          <input className={ui.input} value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <button type="button" className={ui.button} onClick={search} disabled={q.trim().length < 2}>
          {t("search")}
        </button>
        {hits.length ? (
          <select
            aria-label={t("contact")}
            className={ui.input}
            value={contact?.id ?? ""}
            onChange={(e) => setContact(hits.find((h) => h.id === e.target.value) ?? null)}
          >
            <option value="">{t("choose")}</option>
            {hits.map((h) => (
              <option key={h.id} value={h.id}>
                {h.display_name}
              </option>
            ))}
          </select>
        ) : null}
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("deleteAfterLabel")}</span>
          <input type="date" className={ui.input} value={deleteAfter} onChange={(e) => setDeleteAfter(e.target.value)} />
        </label>
        <button
          type="button"
          className={ui.primary}
          disabled={busy || !contact || !deleteAfter}
          onClick={async () => {
            if (await run("/api/bff/letting/prospects", "POST", { unit_id: unitId, contact_id: contact?.id, delete_after: deleteAfter })) {
              setContact(null);
              setHits([]);
              setQ("");
            }
          }}
        >
          {t("add")}
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
