"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Accepted upload types: images including HEIC and PDF (M31). */
const UPLOAD_ACCEPT = "image/jpeg,image/png,image/heic,image/heif,application/pdf";

type PropertyItem = { id: string; number: string; name: string };
type UnitItem = { id: string; number: string; label: string | null };
type CategoryItem = { id: string; code: string; name: string; drive_folder: string | null };
type ContractItem = { id: string; number: string; party_name?: string | null; start_date: string; end_date: string | null };
type ContactItem = { id: string; display_name: string };
type Filing = {
  routed: boolean;
  status?: "pending" | "submitted" | "done" | "failed";
  last_error?: string | null;
};

/** Upload into the CRM with the object (and optionally the unit) it belongs to (26.09.2026),
 *  plus category, contract and contact (Package F, handbook Objektordner). With the objektakte
 *  upload switched on, the document goes to objektakte, which files it in the Drive structure
 *  of the object (owner and tenant files) and in Paperless; otherwise the CRM's own mirrors
 *  apply and the category decides the Drive folder. The filing state is shown right after the
 *  upload. */
export function DmsUpload() {
  const t = useTranslations("DmsSearch.upload");
  const [properties, setProperties] = useState<PropertyItem[]>([]);
  const [propertyId, setPropertyId] = useState("");
  const [units, setUnits] = useState<UnitItem[]>([]);
  const [unitId, setUnitId] = useState("");
  const [categories, setCategories] = useState<CategoryItem[]>([]);
  const [categoryId, setCategoryId] = useState("");
  const [contracts, setContracts] = useState<ContractItem[]>([]);
  const [contractId, setContractId] = useState("");
  const [contactQuery, setContactQuery] = useState("");
  const [contactHits, setContactHits] = useState<ContactItem[]>([]);
  const [contact, setContact] = useState<ContactItem | null>(null);
  const [title, setTitle] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Tenant switch (S12-06, default off): direct upload to object storage with a signed URL.
  const [directUpload, setDirectUpload] = useState(false);
  const [done, setDone] = useState<{ id: string; filing: Filing | null } | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      const [props, cats, direct] = await Promise.all([
        bff<{ items: PropertyItem[] }>("/api/bff/properties?page_size=200"),
        bff<CategoryItem[]>("/api/bff/document-categories"),
        bff<{ enabled: boolean }>("/api/bff/document-direct-upload"),
      ]);
      if (!active) return;
      if (direct.ok) setDirectUpload(direct.data.enabled === true);
      if (props.ok) setProperties(props.data.items);
      if (cats.ok) setCategories(cats.data);
    })();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    setUnits([]);
    setUnitId("");
    if (!propertyId) return;
    let active = true;
    void (async () => {
      const res = await bff<{ items: UnitItem[] } | UnitItem[]>(`/api/bff/properties/${propertyId}/units`);
      if (!active || !res.ok) return;
      setUnits(Array.isArray(res.data) ? res.data : res.data.items);
    })();
    return () => {
      active = false;
    };
  }, [propertyId]);

  // Contracts of the unit, else of the whole property.
  useEffect(() => {
    setContracts([]);
    setContractId("");
    if (!propertyId) return;
    let active = true;
    void (async () => {
      const query = unitId ? `unit_id=${encodeURIComponent(unitId)}` : `property_id=${encodeURIComponent(propertyId)}`;
      const res = await bff<ContractItem[]>(`/api/bff/contracts?${query}&limit=200`);
      if (active && res.ok) setContracts(res.data);
    })();
    return () => {
      active = false;
    };
  }, [propertyId, unitId]);

  async function searchContacts() {
    const q = contactQuery.trim();
    if (!q) return;
    const res = await bff<{ items?: ContactItem[] } | ContactItem[]>(`/api/bff/contacts?q=${encodeURIComponent(q)}&page_size=10`);
    if (res.ok) setContactHits(Array.isArray(res.data) ? res.data : (res.data.items ?? []));
  }

  /** Signed URL upload; returns null when the intent or the PUT fails (CORS, unreachable
   *  endpoint), so that the caller falls back to the upload through the API. */
  async function uploadDirect(file: File, links: { entity_type: string; entity_id: string; role: string }[]) {
    const intent = await bff<{ upload_id: string; url: string; headers: Record<string, string> }>("/api/bff/documents/uploads", {
      method: "POST",
      body: JSON.stringify({ filename: file.name, mime_type: file.type, size: file.size }),
    });
    if (!intent.ok) return null;
    try {
      const put = await fetch(intent.data.url, { method: "PUT", headers: intent.data.headers, body: file });
      if (!put.ok) return null;
    } catch {
      return null;
    }
    return bff<{ id: string }>(`/api/bff/documents/uploads/${intent.data.upload_id}/complete`, {
      method: "POST",
      body: JSON.stringify({
        filename: file.name,
        mime_type: file.type,
        title: title.trim() || null,
        category_id: categoryId || null,
        links,
      }),
    });
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const file = fileRef.current?.files?.[0] ?? cameraRef.current?.files?.[0];
    if (!file || !propertyId) {
      setError(t("errors.missing"));
      return;
    }
    setBusy(true);
    setError(null);
    setDone(null);
    const links = [{ entity_type: unitId ? "unit" : "property", entity_id: unitId || propertyId, role: "original" }];
    if (contractId) links.push({ entity_type: "contract", entity_id: contractId, role: "original" });
    if (contact) links.push({ entity_type: "contact", entity_id: contact.id, role: "original" });
    let res: Awaited<ReturnType<typeof bff<{ id: string }>>> | null = null;
    if (directUpload && file.type) {
      res = await uploadDirect(file, links);
    }
    if (res === null) {
      const body = new FormData();
      body.set("file", file);
      if (title.trim()) body.set("title", title.trim());
      if (categoryId) body.set("category_id", categoryId);
      body.set("links", JSON.stringify(links));
      res = await bff<{ id: string }>("/api/bff/documents", { method: "POST", body });
    }
    if (!res.ok) {
      setBusy(false);
      setError(res.message);
      return;
    }
    const filing = await bff<Filing>(`/api/bff/integrations/objektakte/documents/${res.data.id}/filing`);
    setBusy(false);
    setDone({ id: res.data.id, filing: filing.ok ? filing.data : null });
    setTitle("");
    if (fileRef.current) fileRef.current.value = "";
    if (cameraRef.current) cameraRef.current.value = "";
  };

  const contractLabel = (c: ContractItem) =>
    [c.number, c.party_name || null, [formatDate(c.start_date), c.end_date ? `bis ${formatDate(c.end_date)}` : null].filter(Boolean).join(" ")]
      .filter(Boolean)
      .join(", ");

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-label={t("title")}>
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className="text-sm text-muted">{t("intro")}</p>
      <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => void submit(e)} data-testid="dms-upload-form">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-muted">{t("file")}</span>
          <input ref={fileRef} type="file" className={ui.input} aria-label={t("file")} accept={UPLOAD_ACCEPT} />
        </label>
        {/* Camera on phones and tablets (M31): second input with capture, the first chosen file wins. */}
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-muted">{t("camera")}</span>
          <input ref={cameraRef} type="file" className={ui.input} aria-label={t("camera")} accept="image/*" capture="environment" />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-muted">{t("property")}</span>
          <select className={`${ui.input} w-auto`} value={propertyId} onChange={(e) => setPropertyId(e.target.value)} aria-label={t("property")}>
            <option value="">{t("choose")}</option>
            {properties.map((p) => (
              <option key={p.id} value={p.id}>
                {p.number} {p.name}
              </option>
            ))}
          </select>
        </label>
        {units.length > 0 ? (
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted">{t("unit")}</span>
            <select className={`${ui.input} w-auto`} value={unitId} onChange={(e) => setUnitId(e.target.value)} aria-label={t("unit")}>
              <option value="">{t("wholeProperty")}</option>
              {units.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.label ?? u.number}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-muted">{t("category")}</span>
          <select className={`${ui.input} w-auto`} value={categoryId} onChange={(e) => setCategoryId(e.target.value)} aria-label={t("category")}>
            <option value="">{t("categoryAuto")}</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.drive_folder ? `${c.name} (${c.drive_folder})` : c.name}
              </option>
            ))}
          </select>
        </label>
        {propertyId ? (
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted">{t("contract")}</span>
            <select className={`${ui.input} w-auto`} value={contractId} onChange={(e) => setContractId(e.target.value)} aria-label={t("contract")}>
              <option value="">{t("noContract")}</option>
              {contracts.map((c) => (
                <option key={c.id} value={c.id}>
                  {contractLabel(c)}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <label className="flex min-w-64 flex-1 flex-col gap-1 text-sm">
          <span className="text-muted">{t("titleField")}</span>
          <input className={ui.input} value={title} maxLength={300} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <div className="flex w-full flex-wrap items-end gap-2" data-testid="dms-upload-contact">
          <label className="flex min-w-64 flex-col gap-1 text-sm">
            <span className="text-muted">{t("contact")}</span>
            <input
              className={ui.input}
              value={contactQuery}
              placeholder={t("contactPlaceholder")}
              aria-label={t("contact")}
              onChange={(e) => setContactQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void searchContacts();
                }
              }}
            />
          </label>
          <button type="button" className={ui.buttonSm} onClick={() => void searchContacts()}>
            {t("contactSearch")}
          </button>
          {contact ? (
            <span className={ui.badgeGold}>
              {contact.display_name}
              <button type="button" className="ml-1 underline" onClick={() => setContact(null)} aria-label={t("contactRemove")}>
                ×
              </button>
            </span>
          ) : null}
          {contactHits.length ? (
            <ul className="flex flex-wrap gap-1" aria-label={t("contactHits")}>
              {contactHits.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    className={ui.badge}
                    onClick={() => {
                      setContact(c);
                      setContactHits([]);
                      setContactQuery("");
                    }}
                  >
                    {c.display_name}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <button type="submit" className={ui.primary} disabled={busy}>
          {t("submit")}
        </button>
      </form>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {done ? (
        <p className={ui.success} data-testid="dms-upload-done">
          {done.filing?.routed ? t("routed") : t("notRouted")}{" "}
          <Link href={`/dokumente/${done.id}`} className="underline">
            {t("open")}
          </Link>
        </p>
      ) : null}
    </section>
  );
}
