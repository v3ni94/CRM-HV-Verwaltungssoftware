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

type ListKind = "missing" | "documents";

/** M35 Stufe 4, Teil Listengenerierung: Anforderungsliste fehlender Unterlagen (je Objekt oder
 * über alle Objekte) und Dokumentenübersicht je Kategorie, jeweils mit CSV-Download. Nur
 * lesend, spiegelt `/api/v1/objektakte/lists/...` und `/api/v1/objektakte/properties/{id}/lists/...`. */
export function ObjektakteLists({ properties }: { properties: PropertyOption[] }) {
  const t = useTranslations("Objektakte.lists");
  const [kind, setKind] = useState<ListKind>("missing");
  const [propertyId, setPropertyId] = useState<string>("");
  const [onlyIncomplete, setOnlyIncomplete] = useState(true);
  const [missing, setMissing] = useState<MissingEntry[]>([]);
  const [documents, setDocuments] = useState<DocumentsOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const csvPath = () => {
    if (kind === "documents") {
      return propertyId ? `/api/bff/objektakte/properties/${propertyId}/lists/documents/export` : null;
    }
    if (propertyId) return `/api/bff/objektakte/properties/${propertyId}/lists/missing-documents/export`;
    const params = new URLSearchParams();
    if (onlyIncomplete) params.set("only_incomplete", "true");
    return `/api/bff/objektakte/lists/missing-documents/export?${params.toString()}`;
  };

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      setError(null);
      if (kind === "documents") {
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
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("property")}</span>
          <select className={ui.input} value={propertyId} onChange={(e) => setPropertyId(e.target.value)}>
            <option value="">{kind === "documents" ? t("chooseProperty") : t("allProperties")}</option>
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
      </div>

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
