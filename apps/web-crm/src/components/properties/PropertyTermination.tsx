"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { StatusChip } from "@/components/ui/StatusChip";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type Termination = {
  id: string;
  terminated_by: "manager" | "owner" | "hoa" | "other";
  notice_date: string;
  effective_date: string;
  successor_manager_contact_id: string | null;
  successor_manager_name?: string | null;
  successor_owner_contact_id: string | null;
  successor_owner_name?: string | null;
  notice_document_id: string | null;
  notice_document_title?: string | null;
  note: string | null;
  created_at: string;
};

type Hit = { id: string; display_name: string };
const BY = ["manager", "owner", "hoa", "other"] as const;

function dmy(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}.${m}.${y}`;
}

/** Kontaktsuche für Nachfolger (Name, Datensparsamkeit): tippen, Treffer wählen, wieder entfernen. */
function SuccessorField({ label, value, onChange }: { label: string; value: Hit | null; onChange: (hit: Hit | null) => void }) {
  const t = useTranslations("PropertyTermination");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const search = async (q: string) => {
    setQuery(q);
    if (q.trim().length < 2) {
      setHits([]);
      return;
    }
    const res = await bff<{ items: Hit[] }>(`/api/bff/contacts?q=${encodeURIComponent(q.trim())}&page_size=8`);
    setHits(res.ok ? res.data.items.map((c) => ({ id: c.id, display_name: c.display_name })) : []);
  };
  return (
    <div className="flex flex-col gap-1">
      <label className={ui.label}>
        {label}
        {value ? (
          <span className="mt-1 flex items-center gap-2 text-sm text-fg">
            <span className={ui.badgeGold}>{value.display_name}</span>
            <button type="button" className={ui.buttonSm} onClick={() => onChange(null)}>
              {t("clear")}
            </button>
          </span>
        ) : (
          <input className={ui.input} value={query} onChange={(e) => void search(e.target.value)} placeholder={t("searchPlaceholder")} />
        )}
      </label>
      {!value && hits.length > 0 ? (
        <ul className="flex flex-wrap gap-1">
          {hits.map((h) => (
            <li key={h.id}>
              <button
                type="button"
                className={ui.buttonSm}
                onClick={() => {
                  onChange(h);
                  setHits([]);
                  setQuery("");
                }}
              >
                {h.display_name}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/**
 * Verwaltung beenden (operator 27.09.2026): Formular mit Bestätigung, das
 * POST /properties/{id}/terminate aufruft; bei deaktiviertem Objekt ein Banner mit den Daten
 * der Beendigung und für den Superadmin die Schaltfläche Wieder aktivieren
 * (POST /properties/{id}/reactivate). Das Kündigungsschreiben wird über den bestehenden
 * Dokumentenupload abgelegt und mit dem Objekt verknüpft.
 */
export function PropertyTermination({
  propertyId,
  status,
  termination,
  canEdit,
  isSuperadmin,
}: {
  propertyId: string;
  status: string;
  termination: Termination | null;
  canEdit: boolean;
  isSuperadmin: boolean;
}) {
  const t = useTranslations("PropertyTermination");
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [terminatedBy, setTerminatedBy] = useState<(typeof BY)[number]>("hoa");
  const [noticeDate, setNoticeDate] = useState("");
  const [effectiveDate, setEffectiveDate] = useState("");
  const [manager, setManager] = useState<Hit | null>(null);
  const [owner, setOwner] = useState<Hit | null>(null);
  const [document, setDocument] = useState<{ id: string; title: string } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reactivating, setReactivating] = useState(false);

  const terminated = status === "terminated";
  const datesMissing = noticeDate === "" || effectiveDate === "";
  const datesWrong = !datesMissing && effectiveDate < noticeDate;
  const hint = datesMissing ? t("datesRequired") : datesWrong ? t("datesOrdered") : null;

  const reset = () => {
    setOpen(false);
    setConfirming(false);
    setManager(null);
    setOwner(null);
    setDocument(null);
    setNote("");
    setNoticeDate("");
    setEffectiveDate("");
    setError(null);
  };

  async function upload(file: File) {
    setUploading(true);
    setError(null);
    const form = new FormData();
    form.set("file", file);
    form.set("title", file.name);
    form.set("links", JSON.stringify([{ entity_type: "property", entity_id: propertyId, role: "attachment" }]));
    const res = await bff<{ id: string; title: string }>("/api/bff/documents", { method: "POST", body: form });
    setUploading(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setDocument({ id: res.data.id, title: res.data.title ?? file.name });
  }

  async function save() {
    setBusy(true);
    setError(null);
    const body: Record<string, unknown> = { terminated_by: terminatedBy, notice_date: noticeDate, effective_date: effectiveDate };
    if (manager) body.successor_manager_contact_id = manager.id;
    if (owner) body.successor_owner_contact_id = owner.id;
    if (document) body.notice_document_id = document.id;
    if (note.trim()) body.note = note.trim();
    const res = await bff<Termination>(`/api/bff/properties/${propertyId}/terminate`, { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      setConfirming(false);
      return;
    }
    reset();
    router.refresh();
  }

  async function reactivate() {
    setBusy(true);
    setError(null);
    const res = await bff<{ status: string }>(`/api/bff/properties/${propertyId}/reactivate`, { method: "POST" });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setReactivating(false);
    router.refresh();
  }

  if (terminated) {
    return (
      <section className={`${ui.card} border-l-4 border-l-border`} data-testid="property-terminated" aria-labelledby="termination-banner-title">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="termination-banner-title" className={`${ui.subtitle} flex items-center gap-2`}>
            {t("bannerTitle")} <StatusChip domain="property" status="terminated" />
          </h2>
          {isSuperadmin && !reactivating ? (
            <button type="button" className={ui.buttonSm} onClick={() => setReactivating(true)}>
              {t("reactivate")}
            </button>
          ) : null}
        </div>
        {termination ? (
          <div className="mt-2 flex flex-col gap-1 text-sm">
            <p>{t("bannerText", { date: dmy(termination.effective_date), by: t(`by.${termination.terminated_by}`), notice: dmy(termination.notice_date) })}</p>
            <p className="flex flex-wrap gap-x-4">
              <span>
                {t("successorManager")}:{" "}
                {termination.successor_manager_contact_id ? (
                  <Link href={`/kontakte/${termination.successor_manager_contact_id}`} className="font-medium hover:underline">
                    {termination.successor_manager_name ?? termination.successor_manager_contact_id}
                  </Link>
                ) : (
                  <span className="text-muted">{t("bannerNoSuccessor")}</span>
                )}
              </span>
              <span>
                {t("successorOwner")}:{" "}
                {termination.successor_owner_contact_id ? (
                  <Link href={`/kontakte/${termination.successor_owner_contact_id}`} className="font-medium hover:underline">
                    {termination.successor_owner_name ?? termination.successor_owner_contact_id}
                  </Link>
                ) : (
                  <span className="text-muted">{t("bannerNoSuccessor")}</span>
                )}
              </span>
            </p>
            {termination.notice_document_id ? (
              <p>
                <Link href={`/dokumente/${termination.notice_document_id}`} className="hover:underline">
                  {t("openDocument")}
                  {termination.notice_document_title ? ` (${termination.notice_document_title})` : ""}
                </Link>
              </p>
            ) : null}
            {termination.note ? <p className="text-muted">{termination.note}</p> : null}
            <p className="text-xs text-muted">{t("recordedBy", { date: dmy(termination.created_at) })}</p>
          </div>
        ) : null}
        {!isSuperadmin ? <p className="mt-2 text-xs text-muted">{t("reactivateHint")}</p> : null}
        {reactivating ? (
          <div className="mt-3 flex flex-col gap-2 border-t border-border pt-3" data-testid="reactivate-dialog">
            <p className="text-sm">{t("reactivateConfirm")}</p>
            <div className={ui.formActions}>
              <button type="button" className={ui.primary} disabled={busy} onClick={() => void reactivate()}>
                {t("reactivateConfirmButton")}
              </button>
              <button type="button" className={ui.button} disabled={busy} onClick={() => setReactivating(false)}>
                {t("cancel")}
              </button>
            </div>
          </div>
        ) : null}
        {error ? (
          <p role="alert" className={`${ui.error} mt-2`}>
            {error}
          </p>
        ) : null}
      </section>
    );
  }

  if (!canEdit) return null;

  return (
    <section className={ui.card} data-testid="property-termination">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className={ui.subtitle}>{t("title")}</h2>
        {!open ? (
          <button type="button" className={ui.buttonSm} onClick={() => setOpen(true)}>
            {t("open")}
          </button>
        ) : null}
      </div>
      <p className="mt-1 text-sm text-muted">{t("intro")}</p>
      {open ? (
        <div role="dialog" aria-modal="false" aria-labelledby="termination-dialog-title" className="mt-3 flex flex-col gap-3 border-t border-border pt-3" data-testid="termination-dialog">
          <h3 id="termination-dialog-title" className="font-medium">
            {confirming ? t("confirmTitle") : t("title")}
          </h3>
          {confirming ? (
            <>
              <p className="text-sm">{t("confirmText", { date: dmy(effectiveDate), by: t(`by.${terminatedBy}`), notice: dmy(noticeDate) })}</p>
              <div className={ui.formActions}>
                <button type="button" className={ui.danger} disabled={busy} onClick={() => void save()}>
                  {t("confirm")}
                </button>
                <button type="button" className={ui.button} disabled={busy} onClick={() => setConfirming(false)}>
                  {t("back")}
                </button>
              </div>
            </>
          ) : (
            <>
              <div className="grid gap-3 sm:grid-cols-3">
                <label className={ui.label}>
                  {t("terminatedBy")}
                  <select className={ui.input} value={terminatedBy} onChange={(e) => setTerminatedBy(e.target.value as (typeof BY)[number])}>
                    {BY.map((b) => (
                      <option key={b} value={b}>
                        {t(`by.${b}`)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className={ui.label}>
                  {t("noticeDate")}
                  <input type="date" className={ui.input} value={noticeDate} onChange={(e) => setNoticeDate(e.target.value)} />
                </label>
                <label className={ui.label}>
                  {t("effectiveDate")}
                  <input type="date" className={ui.input} value={effectiveDate} onChange={(e) => setEffectiveDate(e.target.value)} />
                </label>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <SuccessorField label={t("successorManager")} value={manager} onChange={setManager} />
                <SuccessorField label={t("successorOwner")} value={owner} onChange={setOwner} />
              </div>
              <div className="flex flex-col gap-1">
                <span className={ui.label}>{t("noticeDocument")}</span>
                {document ? (
                  <span className="flex items-center gap-2 text-sm">
                    <span>{t("uploaded", { title: document.title })}</span>
                    <button type="button" className={ui.buttonSm} onClick={() => setDocument(null)}>
                      {t("removeDocument")}
                    </button>
                  </span>
                ) : (
                  <label className="text-sm">
                    <span className="sr-only">{t("upload")}</span>
                    <input
                      type="file"
                      aria-label={t("upload")}
                      disabled={uploading}
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) void upload(file);
                      }}
                    />
                    {uploading ? <span className="ml-2 text-muted">{t("uploading")}</span> : null}
                  </label>
                )}
              </div>
              <label className={ui.label}>
                {t("note")}
                <textarea className={ui.input} rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
              </label>
              {hint ? <p className={ui.help}>{hint}</p> : null}
              <div className={ui.formActions}>
                <button type="button" className={ui.primary} disabled={datesMissing || datesWrong || uploading} onClick={() => setConfirming(true)}>
                  {t("next")}
                </button>
                <button type="button" className={ui.button} onClick={reset}>
                  {t("cancel")}
                </button>
              </div>
            </>
          )}
          {error ? (
            <p role="alert" className={ui.error}>
              {error}
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
