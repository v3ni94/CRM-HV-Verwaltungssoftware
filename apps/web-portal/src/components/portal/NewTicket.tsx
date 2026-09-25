"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Neue Schadensmeldung (M21): Titel, Beschreibung und optional ein Foto. Die API verknüpft
 *  hochgeladene Fotos nicht mit der Meldung selbst; die Beleg-ID wird deshalb in der
 *  Beschreibung vermerkt, damit die Verwaltung das Foto zuordnen kann. */
export function NewTicket() {
  const t = useTranslations("Tickets");
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (title.trim().length < 3) {
      setError(t("titleRequired"));
      return;
    }
    if (description.trim().length < 3) {
      setError(t("descriptionRequired"));
      return;
    }
    setBusy(true);
    let finalDescription = description.trim();
    if (photo) {
      const form = new FormData();
      form.append("file", photo);
      const upload = await bff<{ id: string }>("/api/bff/portal/uploads", { method: "POST", body: form });
      if (!upload.ok) {
        setBusy(false);
        setError(upload.message);
        return;
      }
      finalDescription += `\n\nFoto-Beleg: ${photo.name} (Beleg-ID ${upload.data.id})`;
    }
    const result = await bff<{ id: string }>("/api/bff/portal/tickets", {
      method: "POST",
      body: JSON.stringify({ title: title.trim(), description: finalDescription }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setDone(true);
    setTitle("");
    setDescription("");
    setPhoto(null);
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} noValidate className={`${ui.card} flex flex-col gap-3`}>
      <h2 className={ui.h2}>{t("new")}</h2>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {done ? <p className={ui.success}>{t("submitted")}</p> : null}
      <div>
        <label htmlFor="ticket-title" className={ui.label}>
          {t("titleField")}
        </label>
        <input id="ticket-title" className={ui.input} value={title} onChange={(e) => setTitle(e.target.value)} />
      </div>
      <div>
        <label htmlFor="ticket-description" className={ui.label}>
          {t("description")}
        </label>
        <textarea
          id="ticket-description"
          rows={4}
          className={ui.input}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      <div>
        <label htmlFor="ticket-photo" className={ui.label}>
          {t("photo")}
        </label>
        <input
          id="ticket-photo"
          type="file"
          accept="image/*"
          className={ui.input}
          onChange={(e) => setPhoto(e.target.files?.[0] ?? null)}
        />
      </div>
      <div className={ui.formActions}>
        <button type="submit" className={`${ui.primary} ${ui.actionFull}`} disabled={busy}>
          {t("submit")}
        </button>
      </div>
    </form>
  );
}
