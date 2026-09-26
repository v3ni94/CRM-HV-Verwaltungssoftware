"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export type PropertyOption = { id: string; number: string; name: string };

type MissingClass = { document_category_id: string; code: string; name: string };
export type MissingEntry = {
  property_id: string;
  property_number: string;
  property_name: string;
  management_type: string;
  missing: MissingClass[];
  satisfied_count: number;
  complete: boolean;
};

type DocumentRow = {
  document_id: string;
  title: string;
  filename: string;
  mime_type: string;
  created_at: string;
  source_system: string | null;
  duplicate: boolean;
};
export type DocumentsOverview = {
  property_id: string;
  property_number: string;
  property_name: string;
  management_type: string;
  total: number;
  groups: { category_id: string | null; code: string; name: string; count: number; documents: DocumentRow[] }[];
};

type PersonRow = {
  unit_id: string;
  unit_number: string;
  unit_label: string | null;
  contract_id: string;
  contract_number: string;
  contract_start: string;
  contract_end: string | null;
  party_name: string;
  contact_id: string | null;
  name: string;
  street: string;
  postal_code: string;
  city: string;
  email: string;
  phone: string;
};
export type PersonsList = {
  property_id: string;
  property_number: string;
  property_name: string;
  management_type: string;
  kind: "owners" | "tenants";
  reference_date: string;
  total: number;
  rows: PersonRow[];
};

type ListKind = "missing" | "documents" | "owners" | "tenants";
/** API path segment of a list kind (`/lists/<kind>`). */
const API_KIND: Record<ListKind, string> = {
  missing: "missing-documents",
  documents: "documents",
  owners: "owners",
  tenants: "tenants",
};

/** M35 Stufe 4, Teil Listengenerierung: Anforderungsliste fehlender Unterlagen (je Objekt oder
 * über alle Objekte), Dokumentenübersicht je Kategorie sowie Eigentümer- und Mieterliste je
 * Objekt, jeweils mit CSV-Download und Ablage als Dokument beim Objekt. Spiegelt
 * `/api/v1/objektakte/lists/...` und `/api/v1/objektakte/properties/{id}/lists/...`. */
export function ObjektakteLists({ properties }: { properties: PropertyOption[] }) {
  const t = useTranslations("Objektakte.lists");
  const [kind, setKind] = useState<ListKind>("missing");
  const [propertyId, setPropertyId] = useState<string>("");
  const [onlyIncomplete, setOnlyIncomplete] = useState(true);
  const [missing, setMissing] = useState<MissingEntry[]>([]);
  const [documents, setDocuments] = useState<DocumentsOverview | null>(null);
  const [persons, setPersons] = useState<PersonsList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [storing, setStoring] = useState(false);
  const [storedTitle, setStoredTitle] = useState<string | null>(null);

  const needsProperty = kind !== "missing";
  const csvPath = () => {
    if (needsProperty) {
      return propertyId ? `/api/bff/objektakte/properties/${propertyId}/lists/${API_KIND[kind]}/export` : null;
    }
    if (propertyId) return `/api/bff/objektakte/properties/${propertyId}/lists/missing-documents/export`;
    const params = new URLSearchParams();
    if (onlyIncomplete) params.set("only_incomplete", "true");
    return `/api/bff/objektakte/lists/missing-documents/export?${params.toString()}`;
  };

  async function storeAsDocument() {
    if (!propertyId) return;
    setStoring(true);
    setError(null);
    setStoredTitle(null);
    const res = await bff<{ id: string; title: string }>(
      `/api/bff/objektakte/properties/${propertyId}/lists/${API_KIND[kind]}/store`,
      { method: "POST" },
    );
    setStoring(false);
    if (res.ok) setStoredTitle(res.data.title);
    else setError(res.message);
  }

  useEffect(() => {
    let cancelled = false;
    setStoredTitle(null);
    void (async () => {
      setLoading(true);
      setError(null);
      if (kind === "owners" || kind === "tenants") {
        if (!propertyId) {
          setPersons(null);
          setLoading(false);
          return;
        }
        const res = await bff<PersonsList>(`/api/bff/objektakte/properties/${propertyId}/lists/${kind}`);
        if (cancelled) return;
        if (res.ok) setPersons(res.data);
        else setError(res.message);
      } else if (kind === "documents") {
        if (!propertyId) {
          setDocuments(null);
          setLoading(false);
          return;
        }
        const res = await bff<DocumentsOverview>(`/api/bff/objektakte/properties/${propertyId}/lists/documents`);
        if (cancelled) return;
        if (res.ok) setDocuments(res.data);
        else setError(res.message);
      } else if (propertyId) {
        const res = await bff<MissingEntry>(`/api/bff/objektakte/properties/${propertyId}/lists/missing-documents`);
        if (cancelled) return;
        if (res.ok) setMissing([res.data]);
        else setError(res.message);
      } else {
        const params = new URLSearchParams();
        if (onlyIncomplete) params.set("only_incomplete", "true");
        const res = await bff<{ items: MissingEntry[]; total: number }>(
          `/api/bff/objektakte/lists/missing-documents?${params.toString()}`,
        );
        if (cancelled) return;
        if (res.ok) setMissing(res.data.items);
        else setError(res.message);
      }
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [kind, propertyId, onlyIncomplete]);

  const download = csvPath();

  return (
    <section className={`${ui.card} flex flex-col gap-4`} aria-label={t("title")}>
      <div className="flex flex-col gap-1">
        <h2 className={ui.h2}>{t("title")}</h2>
        <p className={ui.help}>{t("intro")}</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("kind")}</span>
          <select className={ui.input} value={kind} onChange={(e) => setKind(e.target.value as ListKind)}>
            <option value="missing">{t("kindMissing")}</option>
            <option value="documents">{t("kindDocuments")}</option>
            <option value="owners">{t("kindOwners")}</option>
            <option value="tenants">{t("kindTenants")}</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("property")}</span>
          <select className={ui.input} value={propertyId} onChange={(e) => setPropertyId(e.target.value)}>
            <option value="">{needsProperty ? t("chooseProperty") : t("allProperties")}</option>
            {properties.map((p) => (
              <option key={p.id} value={p.id}>
                {p.number} {p.name}
              </option>
            ))}
          </select>
        </label>
        {kind === "missing" && !propertyId ? (
          <label className="flex items-end gap-2 pb-2 text-sm">
            <input type="checkbox" checked={onlyIncomplete} onChange={(e) => setOnlyIncomplete(e.target.checked)} />
            {t("onlyIncomplete")}
          </label>
        ) : null}
      </div>

      <div className={ui.formActions}>
        {download ? (
          <a className={`${ui.secondary} ${ui.actionFull}`} href={download} download>
            {t("downloadCsv")}
          </a>
        ) : null}
        {propertyId ? (
          <button
            type="button"
            className={`${ui.secondary} ${ui.actionFull}`}
            disabled={storing || loading}
            onClick={storeAsDocument}
            data-testid="objektakte-list-store"
          >
            {storing ? t("storing") : t("storeAsDocument")}
          </button>
        ) : null}
      </div>
      {storedTitle ? (
        <p role="status" className={ui.success} data-testid="objektakte-list-stored">
          {t("stored", { title: storedTitle })}
        </p>
      ) : null}

      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {loading ? <p className={ui.help}>{t("loading")}</p> : null}

      {kind === "missing" && !loading ? (
        missing.length === 0 ? (
          <p className="text-sm text-muted">{t("emptyMissing")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className={ui.table}>
              <thead>
                <tr>
                  <th scope="col">{t("colProperty")}</th>
                  <th scope="col">{t("colManagementType")}</th>
                  <th scope="col">{t("colMissing")}</th>
                  <th scope="col">{t("colSatisfied")}</th>
                </tr>
              </thead>
              <tbody>
                {missing.map((entry) => (
                  <tr key={entry.property_id}>
                    <td>
                      {entry.property_number} {entry.property_name}
                    </td>
                    <td>{entry.management_type}</td>
                    <td>
                      {entry.complete ? (
                        <span className={ui.badgeSuccess}>{t("complete")}</span>
                      ) : (
                        <ul className="flex flex-col gap-0.5">
                          {entry.missing.map((m) => (
                            <li key={m.document_category_id}>{m.name}</li>
                          ))}
                        </ul>
                      )}
                    </td>
                    <td>{entry.satisfied_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : null}

      {(kind === "owners" || kind === "tenants") && !loading ? (
        !propertyId ? (
          <p className="text-sm text-muted">{t("chooseProperty")}</p>
        ) : persons && persons.total > 0 ? (
          <div className="flex flex-col gap-2">
            <p className={ui.help}>
              {t("personsIntro", { date: formatDate(persons.reference_date) })} {t("personsTotal", { count: persons.total })}
            </p>
            <div className="overflow-x-auto">
              <table className={ui.table} data-testid="objektakte-persons">
                <thead>
                  <tr>
                    <th scope="col">{t("colUnit")}</th>
                    <th scope="col">{t("colName")}</th>
                    <th scope="col">{t("colAddress")}</th>
                    <th scope="col">{t("colEmail")}</th>
                    <th scope="col">{t("colPhone")}</th>
                    <th scope="col">{t("colContractStart")}</th>
                  </tr>
                </thead>
                <tbody>
                  {persons.rows.map((r) => (
                    <tr key={`${r.contract_id}-${r.contact_id ?? "party"}`}>
                      <td>
                        {r.unit_number}
                        {r.unit_label ? ` ${r.unit_label}` : ""}
                      </td>
                      <td>{r.name}</td>
                      <td>{[r.street, [r.postal_code, r.city].filter(Boolean).join(" ")].filter(Boolean).join(", ")}</td>
                      <td>{r.email}</td>
                      <td>{r.phone}</td>
                      <td>{formatDate(r.contract_start)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted">{t("emptyPersons")}</p>
        )
      ) : null}

      {kind === "documents" && !loading ? (
        !propertyId ? (
          <p className="text-sm text-muted">{t("chooseProperty")}</p>
        ) : documents && documents.total > 0 ? (
          <div className="flex flex-col gap-4">
            <p className={ui.help}>{t("documentsTotal", { count: documents.total })}</p>
            {documents.groups.map((group) => (
              <div key={group.category_id ?? "none"} className="flex flex-col gap-2">
                <h3 className="text-sm font-semibold">
                  {group.code ? `${group.code} ` : ""}
                  {group.name} ({group.count})
                </h3>
                <div className="overflow-x-auto">
                  <table className={ui.table}>
                    <thead>
                      <tr>
                        <th scope="col">{t("colTitle")}</th>
                        <th scope="col">{t("colFilename")}</th>
                        <th scope="col">{t("colCreated")}</th>
                        <th scope="col">{t("colSource")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {group.documents.map((d) => (
                        <tr key={d.document_id}>
                          <td>
                            {d.title}
                            {d.duplicate ? <span className={`${ui.badgeWarning} ml-2`}>{t("duplicate")}</span> : null}
                          </td>
                          <td>{d.filename}</td>
                          <td>{formatDate(d.created_at)}</td>
                          <td>{d.source_system ?? ""}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted">{t("emptyDocuments")}</p>
        )
      ) : null}
    </section>
  );
}
