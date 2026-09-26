"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type ListingImage = {
  document_id: string;
  link_id: string;
  title: string;
  filename: string;
  mime_type: string;
  size: number;
  created_at: string;
  linked_at: string;
  role: string;
};

const ACCEPT = "image/jpeg,image/png,image/tiff,image/heic";

/** Bilder einer Anzeige (M26-02): Upload als Dokument mit Verknüpfung `entity_type=listing`,
 * Verknüpfen eines vorhandenen Dokuments, Lösen der Verknüpfung (das Dokument bleibt). Die
 * Reihenfolge ist die Reihenfolge der Verknüpfung; `DocumentLink` hat kein Sortierfeld, der
 * OpenImmo-Export übernimmt dieselbe Reihenfolge. Spiegelt `/api/v1/letting/listings/{id}/images`. */
export function ListingImages({ listingId }: { listingId: string }) {
  const t = useTranslations("Broker.detail.images");
  const [images, setImages] = useState<ListingImage[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [documentId, setDocumentId] = useState("");
  const fileInput = useRef<HTMLInputElement | null>(null);
  const base = `/api/bff/letting/listings/${listingId}/images`;

  const load = useCallback(async () => {
    const res = await bff<ListingImage[]>(base);
    if (res.ok) setImages(res.data);
    else setError(res.message);
  }, [base]);

  useEffect(() => {
    void load();
  }, [load]);

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    const body = new FormData();
    body.append("file", file, file.name);
    const res = await bff<ListingImage[]>(base, { method: "POST", body });
    setBusy(false);
    if (res.ok) setImages(res.data);
    else setError(res.message);
    if (fileInput.current) fileInput.current.value = "";
  }

  async function linkExisting(e: React.FormEvent) {
    e.preventDefault();
    const id = documentId.trim();
    if (!id) return;
    setBusy(true);
    setError(null);
    const res = await bff<ListingImage[]>(`${base}/link`, { method: "POST", body: JSON.stringify({ document_id: id }) });
    setBusy(false);
    if (res.ok) {
      setImages(res.data);
      setDocumentId("");
    } else {
      setError(res.message);
    }
  }

  async function remove(image: ListingImage) {
    if (!window.confirm(t("confirmRemove"))) return;
    setBusy(true);
    setError(null);
    const res = await bff<ListingImage[]>(`${base}/${image.document_id}`, { method: "DELETE" });
    setBusy(false);
    if (res.ok) setImages(res.data);
    else setError(res.message);
  }

  return (
    <section className={`${ui.card} flex flex-col gap-4`} aria-label={t("title")} data-testid="listing-images">
      <div className="flex flex-col gap-1">
        <h2 className={ui.h2}>{t("title")}</h2>
        <p className={ui.help}>{t("intro")}</p>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("upload")}</span>
          <input
            ref={fileInput}
            type="file"
            accept={ACCEPT}
            className={ui.input}
            disabled={busy}
            data-testid="listing-image-file"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void upload(file);
            }}
          />
          <span className={ui.help}>{busy ? t("uploading") : t("onlyImages")}</span>
        </label>
        <form onSubmit={linkExisting} className="flex flex-col gap-1 sm:flex-row sm:items-end sm:gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("documentId")}</span>
            <input
              className={ui.input}
              value={documentId}
              onChange={(e) => setDocumentId(e.target.value)}
              placeholder={t("linkExisting")}
              disabled={busy}
              data-testid="listing-image-document-id"
            />
          </label>
          <button type="submit" className={ui.secondary} disabled={busy || !documentId.trim()}>
            {t("link")}
          </button>
        </form>
      </div>
      {images === null ? (
        <p className={ui.help}>{t("loading")}</p>
      ) : images.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <ol className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3" data-testid="listing-image-list">
          {images.map((image, index) => (
            <li key={image.link_id} className="flex flex-col gap-2 rounded-md border border-border p-2">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`${base}/${image.document_id}/content`}
                alt={image.title}
                className="aspect-[4/3] w-full rounded object-cover"
                loading="lazy"
              />
              <div className="flex items-center justify-between gap-2 text-xs">
                <span className={ui.badge}>{t("position", { position: index + 1 })}</span>
                <span className="truncate text-muted" title={image.filename}>
                  {image.filename}
                </span>
              </div>
              <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => remove(image)}>
                {t("remove")}
              </button>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
