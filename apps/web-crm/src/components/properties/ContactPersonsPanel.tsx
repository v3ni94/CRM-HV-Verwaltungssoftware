"use client";
/** Ansprechpartner des Objekts (C2, Stammdaten in der Oberfläche): Liste mit Kontaktname,
 *  Kategorie, Zeitraum und Portalsichtbarkeit; Zuordnen über Kontaktsuche und Katalog
 *  `property_contact_category` (POST /properties/{id}/contacts), Ändern und Beenden über
 *  PATCH /properties/{id}/contacts/{id}. Der Kontakt selbst bleibt unveränderlich: eine
 *  falsche Person wird beendet und neu zugeordnet. Schreibrecht `properties:update`. */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

import { ContactPicker, loadCatalogOptions, todayIso, type ContactHit } from "./ContactPersonsPicker";

export type ContactPersonRow = {
  id: string;
  contact_id: string;
  contact_name?: string | null;
  category_code: string;
  valid_from: string;
  valid_to: string | null;
  visible_in_portal_for: string[];
};

const AUDIENCES = ["tenant", "owner", "provider"] as const;

type Draft = { category_code: string; valid_from: string; valid_to: string; visible_in_portal_for: string[] };

function draftOf(row: ContactPersonRow): Draft {
  return {
    category_code: row.category_code,
    valid_from: row.valid_from,
    valid_to: row.valid_to ?? "",
    visible_in_portal_for: row.visible_in_portal_for,
  };
}

function AudienceBoxes({ value, onChange, label }: { value: string[]; onChange: (v: string[]) => void; label: (a: string) => string }) {
  return (
    <div className="flex flex-wrap gap-3 text-sm">
      {AUDIENCES.map((a) => (
        <label key={a} className="inline-flex items-center gap-1">
          <input
            type="checkbox"
            checked={value.includes(a)}
            onChange={(e) => onChange(e.target.checked ? [...value, a] : value.filter((x) => x !== a))}
          />
          {label(a)}
        </label>
      ))}
    </div>
  );
}

export function ContactPersonsPanel({ propertyId, rows, canEdit }: { propertyId: string; rows: ContactPersonRow[]; canEdit: boolean }) {
  const t = useTranslations("Properties.contactPersons");
  const router = useRouter();
  const [categories, setCategories] = useState<{ code: string; label: string }[]>([]);
  const [adding, setAdding] = useState(false);
  const [contact, setContact] = useState<ContactHit | null>(null);
  const [draft, setDraft] = useState<Draft>({ category_code: "", valid_from: todayIso(), valid_to: "", visible_in_portal_for: [] });
  const [editing, setEditing] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void loadCatalogOptions("property_contact_category").then((options) => {
      if (active) setCategories(options);
    });
    return () => {
      active = false;
    };
  }, []);

  const categoryLabel = (code: string) => categories.find((c) => c.code === code)?.label ?? code;
  const audienceLabel = (a: string) => t(`audience.${a}`);

  const body = (d: Draft) => ({
    category_code: d.category_code,
    valid_from: d.valid_from,
    valid_to: d.valid_to || null,
    visible_in_portal_for: d.visible_in_portal_for,
  });

  const run = async (path: string, method: "POST" | "PATCH", payload: Record<string, unknown>) => {
    setBusy(true);
    setError(null);
    const res = await bff(path, { method, body: JSON.stringify(payload) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return false;
    }
    router.refresh();
    return true;
  };

  const add = async () => {
    if (!contact) return;
    if (await run(`/api/bff/properties/${propertyId}/contacts`, "POST", { contact_id: contact.id, ...body(draft) })) {
      setAdding(false);
      setContact(null);
      setDraft({ category_code: "", valid_from: todayIso(), valid_to: "", visible_in_portal_for: [] });
    }
  };

  const save = async (id: string) => {
    if (!editDraft) return;
    if (await run(`/api/bff/properties/${propertyId}/contacts/${id}`, "PATCH", body(editDraft))) {
      setEditing(null);
      setEditDraft(null);
    }
  };

  const end = async (row: ContactPersonRow) => {
    await run(`/api/bff/properties/${propertyId}/contacts/${row.id}`, "PATCH", { valid_to: todayIso() });
  };

  const today = todayIso();
  const isActive = (row: ContactPersonRow) => row.valid_from <= today && (!row.valid_to || row.valid_to >= today);

  const form = (d: Draft, set: (d: Draft) => void) => (
    <div className="grid gap-3 sm:grid-cols-2">
      <label className={ui.label}>
        {t("category")}
        <select className={ui.input} value={d.category_code} onChange={(e) => set({ ...d, category_code: e.target.value })} required>
          <option value="">{t("chooseCategory")}</option>
          {categories.map((c) => (
            <option key={c.code} value={c.code}>
              {c.label}
            </option>
          ))}
        </select>
      </label>
      <div />
      <label className={ui.label}>
        {t("validFrom")}
        <input type="date" className={ui.input} value={d.valid_from} onChange={(e) => set({ ...d, valid_from: e.target.value })} required />
      </label>
      <label className={ui.label}>
        {t("validTo")}
        <input type="date" className={ui.input} value={d.valid_to} onChange={(e) => set({ ...d, valid_to: e.target.value })} />
      </label>
      <div className="sm:col-span-2">
        <span className={ui.label}>{t("visibleFor")}</span>
        <AudienceBoxes value={d.visible_in_portal_for} onChange={(v) => set({ ...d, visible_in_portal_for: v })} label={audienceLabel} />
      </div>
    </div>
  );

  return (
    <section id="ansprechpartner" className={ui.card} data-testid="property-contact-persons" aria-label={t("title")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className={ui.subtitle}>{t("title")}</h2>
        {canEdit && !adding ? (
          <button type="button" className={ui.buttonSm} onClick={() => setAdding(true)}>
            {t("add")}
          </button>
        ) : null}
      </div>
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-muted">{t("empty")}</p>
      ) : (
        <div className="mt-2 overflow-x-auto">
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("contact")}</th>
                <th>{t("category")}</th>
                <th>{t("validity")}</th>
                <th>{t("visibleFor")}</th>
                {canEdit ? <th /> : null}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className={isActive(row) ? undefined : "text-muted"}>
                  <td>
                    <Link href={`/kontakte/${row.contact_id}`} className="font-medium hover:underline">
                      {row.contact_name ?? row.contact_id}
                    </Link>
                    {editing === row.id && editDraft ? (
                      <div className="mt-2 flex flex-col gap-3 border-t border-border pt-3" data-testid="contact-person-edit">
                        {form(editDraft, setEditDraft)}
                        <div className={ui.formActions}>
                          <button type="button" className={ui.primary} disabled={busy || !editDraft.category_code} onClick={() => void save(row.id)}>
                            {t("save")}
                          </button>
                          <button type="button" className={ui.button} onClick={() => setEditing(null)}>
                            {t("cancel")}
                          </button>
                        </div>
                      </div>
                    ) : null}
                  </td>
                  <td>{categoryLabel(row.category_code)}</td>
                  <td className="whitespace-nowrap">
                    {formatDate(row.valid_from)}
                    {row.valid_to ? ` ${t("until")} ${formatDate(row.valid_to)}` : ""}
                  </td>
                  <td>{row.visible_in_portal_for.length ? row.visible_in_portal_for.map(audienceLabel).join(", ") : t("notVisible")}</td>
                  {canEdit ? (
                    <td className="whitespace-nowrap">
                      <div className="flex gap-1">
                        <button
                          type="button"
                          className={ui.buttonSm}
                          onClick={() => {
                            setEditing(row.id);
                            setEditDraft(draftOf(row));
                          }}
                        >
                          {t("edit")}
                        </button>
                        {isActive(row) ? (
                          <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void end(row)}>
                            {t("end")}
                          </button>
                        ) : null}
                      </div>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {adding ? (
        <div role="dialog" aria-modal="false" aria-label={t("add")} className="mt-3 flex flex-col gap-3 border-t border-border pt-3" data-testid="contact-person-add">
          <ContactPicker label={t("contact")} value={contact} onChange={setContact} testId="contact-person-search" />
          {form(draft, setDraft)}
          <div className={ui.formActions}>
            <button type="button" className={ui.primary} disabled={busy || !contact || !draft.category_code || !draft.valid_from} onClick={() => void add()}>
              {t("assign")}
            </button>
            <button
              type="button"
              className={ui.button}
              onClick={() => {
                setAdding(false);
                setContact(null);
              }}
            >
              {t("cancel")}
            </button>
          </div>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className={`${ui.alert} mt-2`}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
