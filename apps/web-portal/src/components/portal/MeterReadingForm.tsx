"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Zählerstand melden (M21): geht als Vorschlag in die Prüfung der Verwaltung, keine
 *  automatische Übernahme. AM06 (GAJ-401): Foto des Zählers als Ablesebeleg, auch direkt per
 *  Kamera; ohne Foto erscheint ein Hinweis, die Meldung bleibt möglich. */
const MAX_PHOTOS = 5;

/** AN02 (GAJ-401, AM06-01): Mandantenschalter, off ohne Fotohinweis, hint (Standard) mit
 *  Hinweis, required verlangt ein Foto (die API lehnt die Meldung ohne Foto mit 422 ab). */
export type MeterPhotoMode = "off" | "hint" | "required";

export function MeterReadingForm({ photoMode = "hint" }: { photoMode?: MeterPhotoMode }) {
  const t = useTranslations("Meter");
  const tPortal = useTranslations("Portal");
  const [meterId, setMeterId] = useState("");
  const [value, setValue] = useState("");
  const [readAt, setReadAt] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [photos, setPhotos] = useState<File[]>([]);
  const [sentWithoutPhoto, setSentWithoutPhoto] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!meterId.trim()) {
      setError(t("meterIdHint"));
      return;
    }
    if (value.trim() === "") {
      setError(t("valueRequired"));
      return;
    }
    if (!readAt) {
      setError(t("dateRequired"));
      return;
    }
    if (photoMode === "required" && photos.length === 0) {
      setError(t("photoRequired"));
      return;
    }
    setBusy(true);
    const documentIds: string[] = [];
    for (const photo of photos.slice(0, MAX_PHOTOS)) {
      const form = new FormData();
      form.append("file", photo);
      const upload = await bff<{ id: string }>("/api/bff/portal/uploads", { method: "POST", body: form });
      if (!upload.ok) {
        setBusy(false);
        setError(upload.message);
        return;
      }
      documentIds.push(upload.data.id);
    }
    const result = await bff<{ id: string; photo_missing?: boolean }>("/api/bff/portal/meter-readings", {
      method: "POST",
      body: JSON.stringify({
        meter_id: meterId.trim(),
        value: value.trim().replace(",", "."),
        read_at: readAt,
        document_ids: documentIds,
      }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setDone(true);
    setSentWithoutPhoto(Boolean(result.data?.photo_missing));
    setValue("");
    setPhotos([]);
  }

  return (
    <form onSubmit={onSubmit} noValidate className={`${ui.card} flex flex-col gap-3`}>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {done ? <p className={ui.success}>{t("submitted")}</p> : null}
      {done && sentWithoutPhoto ? <p className={ui.notice}>{t("photoMissingSent")}</p> : null}
      <p className={ui.help}>{t("meterIdHint")}</p>
      <div>
        <label htmlFor="meter-id" className={ui.label}>
          {t("meterId")}
        </label>
        <input id="meter-id" className={ui.input} value={meterId} onChange={(e) => setMeterId(e.target.value)} />
      </div>
      <div>
        <label htmlFor="meter-value" className={ui.label}>
          {t("value")}
        </label>
        <input id="meter-value" inputMode="decimal" className={ui.input} value={value} onChange={(e) => setValue(e.target.value)} />
      </div>
      <div>
        <label htmlFor="meter-date" className={ui.label}>
          {t("date")}
        </label>
        <input id="meter-date" type="date" className={ui.input} value={readAt} onChange={(e) => setReadAt(e.target.value)} />
      </div>
      <div>
        <label htmlFor="meter-photo" className={ui.label}>
          {t("photo")}
          {photoMode === "required" ? ` (${t("photoRequiredLabel")})` : ""}
        </label>
        <input
          id="meter-photo"
          type="file"
          accept="image/*"
          multiple
          aria-describedby="meter-photo-hint"
          className={ui.input}
          onChange={(e) => setPhotos(Array.from(e.target.files ?? []).slice(0, MAX_PHOTOS))}
        />
        <label htmlFor="meter-photo-camera" className={`${ui.button} mt-2 inline-block cursor-pointer`}>
          {t("photoCamera")}
          <input
            id="meter-photo-camera"
            type="file"
            accept="image/*"
            capture="environment"
            className="sr-only"
            data-testid="meter-photo-camera"
            onChange={(e) => {
              const shot = Array.from(e.target.files ?? []);
              setPhotos((prev) => [...prev, ...shot].slice(0, MAX_PHOTOS));
            }}
          />
        </label>
        <p id="meter-photo-hint" className={ui.help}>
          {t("photoHint")}
        </p>
        {photos.length === 0 && photoMode === "hint" ? (
          <p className={ui.notice} data-testid="meter-photo-missing">
            {t("photoMissing")}
          </p>
        ) : photos.length > 0 ? (
          <p className={ui.help}>{photos.map((p) => p.name).join(", ")}</p>
        ) : null}
      </div>
      <p className={ui.help}>{tPortal("proposalNotice")}</p>
      <div className={ui.formActions}>
        <button type="submit" className={`${ui.primary} ${ui.actionFull}`} disabled={busy}>
          {t("submit")}
        </button>
      </div>
    </form>
  );
}
