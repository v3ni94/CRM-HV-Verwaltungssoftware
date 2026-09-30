"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export const VACANCY_STATUS = ["open", "advertised", "viewing", "rented", "renovation", "blocked"] as const;

/** Leerstandsmaßnahme je Einheit (M26-04): Status, Sollmiete, Kosten je Monat, Wiedervorlage,
 *  Notiz; Direktaktion Anzeige anlegen (Entwurf). */
export function VacancyMeasure({
  unitId,
  status,
  targetRent,
  monthlyCosts,
  followUpOn,
  note,
  canEdit,
  canCreateListing,
}: {
  unitId: string;
  status: string;
  targetRent: string | null;
  monthlyCosts: string | null;
  followUpOn: string | null;
  note: string | null;
  canEdit: boolean;
  canCreateListing: boolean;
}) {
  const t = useTranslations("Letting");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    status,
    target_rent: targetRent ?? "",
    monthly_costs: monthlyCosts ?? "",
    follow_up_on: followUpOn ?? "",
    note: note ?? "",
  });
  const [saved, setSaved] = useState(status);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [listed, setListed] = useState(false);

  async function save() {
    setBusy(true);
    setError(null);
    const res = await bff<{ status: string }>(`/api/bff/letting/vacancies/${unitId}`, {
      method: "PUT",
      body: JSON.stringify({
        status: form.status,
        target_rent: form.target_rent || null,
        monthly_costs: form.monthly_costs || null,
        follow_up_on: form.follow_up_on || null,
        note: form.note || null,
      }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setSaved(res.data.status);
    setOpen(false);
  }

  async function listing() {
    setBusy(true);
    setError(null);
    const res = await bff<{ id: string }>(`/api/bff/letting/vacancies/${unitId}/listing`, {
      method: "POST",
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setListed(true);
    setSaved((s) => (s === "open" ? "advertised" : s));
  }

  return (
    <div className="flex flex-col gap-1">
      <span className={ui.badge}>{t(`vacancyStatus.${saved as (typeof VACANCY_STATUS)[number]}`)}</span>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {listed ? <p className="text-xs text-muted">{t("listingCreated")}</p> : null}
      {canEdit ? (
        <button type="button" className={ui.buttonSm} onClick={() => setOpen((o) => !o)}>
          {t("measure")}
        </button>
      ) : null}
      {canCreateListing && !listed ? (
        <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void listing()}>
          {t("createListing")}
        </button>
      ) : null}
      {open ? (
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("vacancyStatusLabel")}</span>
            <select
              className={ui.input}
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value })}
            >
              {VACANCY_STATUS.map((s) => (
                <option key={s} value={s}>
                  {t(`vacancyStatus.${s}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("targetRent")}</span>
            <input
              className={ui.input}
              inputMode="decimal"
              value={form.target_rent}
              onChange={(e) => setForm({ ...form, target_rent: e.target.value })}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("monthlyCosts")}</span>
            <input
              className={ui.input}
              inputMode="decimal"
              value={form.monthly_costs}
              onChange={(e) => setForm({ ...form, monthly_costs: e.target.value })}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("followUp")}</span>
            <input
              className={ui.input}
              type="date"
              value={form.follow_up_on}
              onChange={(e) => setForm({ ...form, follow_up_on: e.target.value })}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("vacancyNote")}</span>
            <textarea
              className={ui.input}
              rows={2}
              value={form.note}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
            />
          </label>
          <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void save()}>
            {t("saveMeasure")}
          </button>
        </div>
      ) : null}
    </div>
  );
}
