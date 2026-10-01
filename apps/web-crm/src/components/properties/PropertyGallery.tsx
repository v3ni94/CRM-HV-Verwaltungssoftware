"use client";

import { useTranslations } from "next-intl";
import { useRef, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

const ACCEPT = "image/jpeg,image/png,image/tiff,image/heic";

/** Image gallery of a property (M4-06, 6.2 property.images): document references in display
 *  order. A new image is stored as a regular document linked to the property (type and size
 *  check, metadata removed by the API) and appended to `images`; removing only takes the image
 *  out of the gallery, the document stays in the document store. Every change is one
 *  PATCH /properties/{id} with If-Match (the complete list, so the order is kept). */
export function PropertyGallery({
  propertyId,
  version,
  images: initial,
  canEdit,
}: {
  propertyId: string;
  version: number;
  images: string[];
  canEdit: boolean;
}) {
  const t = useTranslations("PropertyGallery");
  const [images, setImages] = useState<string[]>(initial);
  const [current, setCurrent] = useState(version);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

  async function save(next: string[]): Promise<boolean> {
    const res = await bff<{ version: number; images: string[] }>(`/api/bff/properties/${propertyId}`, {
      method: "PATCH",
      headers: { "if-match": String(current) },
      body: JSON.stringify({ images: next }),
    });
    if (!res.ok) {
      setError(res.status === 412 || res.status === 409 ? t("stale") : res.message);
      return false;
    }
    setImages(res.data?.images ?? next);
    setCurrent(res.data?.version ?? current + 1);
    return true;
  }

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    const body = new FormData();
    body.append("file", file, file.name);
    body.append("links", JSON.stringify([{ entity_type: "property", entity_id: propertyId, role: "attachment" }]));
    const res = await bff<{ id: string }>("/api/bff/documents", { method: "POST", body });
    if (!res.ok) {
      setBusy(false);
      setError(res.message);
    } else {
      await save([...images, res.data.id]);
      setBusy(false);
    }
    if (fileInput.current) fileInput.current.value = "";
  }

  async function move(index: number, delta: number) {
    const target = index + delta;
    if (target < 0 || target >= images.length) return;
    const next = [...images];
    [next[index], next[target]] = [next[target] as string, next[index] as string];
    setBusy(true);
    setError(null);
    await save(next);
    setBusy(false);
  }

  async function remove(index: number) {
    if (!window.confirm(t("confirmRemove"))) return;
    setBusy(true);
    setError(null);
    await save(images.filter((_, i) => i !== index));
    setBusy(false);
  }

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="property-gallery-title" data-testid="property-gallery">
      <div className="flex flex-col gap-1">
        <h2 id="property-gallery-title" className={ui.h2}>
          {t("title")}
        </h2>
        <p className={ui.help}>{t("intro")}</p>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {canEdit ? (
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("upload")}</span>
          <input
            ref={fileInput}
            type="file"
            accept={ACCEPT}
            className={ui.input}
            disabled={busy || images.length >= 50}
            data-testid="property-image-file"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void upload(file);
            }}
          />
          <span className={ui.help}>{busy ? t("saving") : t("onlyImages")}</span>
        </label>
      ) : null}
      {images.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <ol className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3" data-testid="property-image-list">
          {images.map((id, index) => (
            <li key={id} className="flex flex-col gap-2 rounded-md border border-border p-2">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`/api/handover-files/documents/${id}/content`}
                alt={t("imageAlt", { position: index + 1 })}
                className="aspect-[4/3] w-full rounded object-cover"
                loading="lazy"
              />
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className={ui.badge}>{t("position", { position: index + 1 })}</span>
                {canEdit ? (
                  <span className="ml-auto flex gap-1">
                    <button
                      type="button"
                      className={ui.buttonSm}
                      disabled={busy || index === 0}
                      aria-label={t("moveUp", { position: index + 1 })}
                      onClick={() => void move(index, -1)}
                    >
                      {t("up")}
                    </button>
                    <button
                      type="button"
                      className={ui.buttonSm}
                      disabled={busy || index === images.length - 1}
                      aria-label={t("moveDown", { position: index + 1 })}
                      onClick={() => void move(index, 1)}
                    >
                      {t("down")}
                    </button>
                    <button
                      type="button"
                      className={ui.buttonSm}
                      disabled={busy}
                      aria-label={t("removeImage", { position: index + 1 })}
                      onClick={() => void remove(index)}
                    >
                      {t("remove")}
                    </button>
                  </span>
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
