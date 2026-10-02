"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";
import { useBusy } from "@/lib/use-busy";

type Win = {
  id: string;
  starts_at: string;
  ends_at: string;
  text_de: string;
  text_en: string;
  notice_hours: number | null;
  cancelled_at: string | null;
  phase: string;
};

const fmt = (iso: string) => new Date(iso).toLocaleString("de-DE", { timeZone: "Europe/Berlin" });

/** GB16-01: announce, list and cancel maintenance windows (platform administrators). */
export function MaintenanceAdmin() {
  const { busy, guard } = useBusy();
  const t = useTranslations("AD10");
  const [rows, setRows] = useState<Win[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ start: "", end: "", de: "", en: "", notice: "" });

  const load = useCallback(async () => {
    const res = await bff<Win[]>("/api/bff/platform/maintenance-windows");
    if (res.ok) {
      setRows(res.data);
      setError(null);
    } else setError(res.message);
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    const res = await bff("/api/bff/platform/maintenance-windows", {
      method: "POST",
      body: JSON.stringify({
        starts_at: new Date(form.start).toISOString(),
        ends_at: new Date(form.end).toISOString(),
        text_de: form.de,
        text_en: form.en,
        notice_hours: form.notice === "" ? null : Number(form.notice),
      }),
    });
    if (res.ok) {
      setForm({ start: "", end: "", de: "", en: "", notice: "" });
      await load();
    } else setError(res.message);
  }

  async function cancel(id: string) {
    const res = await bff(`/api/bff/platform/maintenance-windows/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ cancel: true }),
    });
    if (res.ok) await load();
    else setError(res.message);
  }

  return (
    <section className={ui.pageGap} aria-labelledby="ad10-windows">
      <h2 id="ad10-windows" className="text-lg font-semibold">
        {t("windowsTitle")}
      </h2>
      <p className={ui.notice}>{t("windowsIntro")}</p>
      {error ? <p className={ui.alert}>{error}</p> : null}
      <form onSubmit={guard(create)} className={`${ui.card} grid gap-3 sm:grid-cols-2`}>
        <label className="block">
          <span className={ui.label}>{t("start")}</span>
          <input className={ui.input} type="datetime-local" required value={form.start} onChange={(e) => setForm({ ...form, start: e.target.value })} />
        </label>
        <label className="block">
          <span className={ui.label}>{t("end")}</span>
          <input className={ui.input} type="datetime-local" required value={form.end} onChange={(e) => setForm({ ...form, end: e.target.value })} />
        </label>
        <label className="block">
          <span className={ui.label}>{t("textDe")}</span>
          <input className={ui.input} required minLength={3} maxLength={500} value={form.de} onChange={(e) => setForm({ ...form, de: e.target.value })} />
        </label>
        <label className="block">
          <span className={ui.label}>{t("textEn")}</span>
          <input className={ui.input} required minLength={3} maxLength={500} value={form.en} onChange={(e) => setForm({ ...form, en: e.target.value })} />
        </label>
        <label className="block">
          <span className={ui.label}>{t("noticeHours")}</span>
          <input className={ui.input} type="number" min={0} max={720} value={form.notice} onChange={(e) => setForm({ ...form, notice: e.target.value })} />
          <span className={ui.help}>{t("noticeHelp")}</span>
        </label>
        <div className="flex items-end">
          <button type="submit" className={ui.primary}>
            {t("announce")}
          </button>
        </div>
      </form>
      {rows.length === 0 ? <p className="text-sm text-muted">{t("noWindows")}</p> : null}
      {rows.length > 0 ? (
        <div className={ui.tableScroll}>
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("start")}</th>
                <th>{t("end")}</th>
                <th>{t("text")}</th>
                <th>{t("phase")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((w) => (
                <tr key={w.id}>
                  <td>{fmt(w.starts_at)}</td>
                  <td>{fmt(w.ends_at)}</td>
                  <td>{w.text_de}</td>
                  <td>{t(`phases.${w.phase}` as never)}</td>
                  <td>
                    {w.phase === "scheduled" || w.phase === "announced" || w.phase === "active" ? (
                      <button disabled={busy} type="button" className={ui.buttonSm} onClick={guard(() => cancel(w.id))}>
                        {t("cancel")}
                      </button>
                    ) : null}
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
