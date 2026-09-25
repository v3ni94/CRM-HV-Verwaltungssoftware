"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import type { PortalContract } from "@/lib/portal";
import { ui } from "@/lib/ui";

/**
 * New damage report. The API (PortalTicketIn) takes title, description and an optional
 * unit_id of an own contract; there is no category or attachment field on the ticket.
 */
export function TicketForm({ contracts }: { contracts: PortalContract[] }) {
  const t = useTranslations("Tickets");
  const router = useRouter();
  const units = contracts.filter((c): c is PortalContract & { unit_id: string } => !!c.unit_id);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [unitId, setUnitId] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{ title?: string; description?: string }>({});
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setCreated(null);
    const errors: { title?: string; description?: string } = {};
    if (title.trim().length < 3) errors.title = t("titleRequired");
    if (description.trim().length < 3) errors.description = t("descriptionRequired");
    setFieldErrors(errors);
    if (errors.title || errors.description) return;
    setSubmitting(true);
    const result = await bff<{ id: string; number: string; status: string }>("/api/bff/portal/tickets", {
      method: "POST",
      body: JSON.stringify({
        title: title.trim(),
        description: description.trim(),
        ...(unitId ? { unit_id: unitId } : {}),
      }),
    });
    setSubmitting(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setCreated(result.data.number);
    setTitle("");
    setDescription("");
    setUnitId("");
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} noValidate className={`${ui.card} flex flex-col gap-3`} aria-label={t("newTitle")}>
      <h2 className={ui.h2}>{t("newTitle")}</h2>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {created ? (
        <p role="status" className={ui.success}>
          {t("created", { number: created })}
        </p>
      ) : null}
      <div>
        <label htmlFor="ticket-title" className={ui.label}>
          {t("fieldTitle")}
        </label>
        <input
          id="ticket-title"
          type="text"
          className={ui.input}
          aria-invalid={!!fieldErrors.title}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <p className={ui.help}>{t("fieldTitleHelp")}</p>
        {fieldErrors.title ? <p className={ui.error}>{fieldErrors.title}</p> : null}
      </div>
      <div>
        <label htmlFor="ticket-description" className={ui.label}>
          {t("fieldDescription")}
        </label>
        <textarea
          id="ticket-description"
          rows={4}
          className={ui.input}
          aria-invalid={!!fieldErrors.description}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        {fieldErrors.description ? <p className={ui.error}>{fieldErrors.description}</p> : null}
      </div>
      {units.length > 0 ? (
        <div>
          <label htmlFor="ticket-unit" className={ui.label}>
            {t("fieldUnit")}
          </label>
          <select id="ticket-unit" className={ui.input} value={unitId} onChange={(e) => setUnitId(e.target.value)}>
            <option value="">{t("unitNone")}</option>
            {units.map((c) => (
              <option key={c.id} value={c.unit_id}>
                {t("unitOption", { number: c.number })}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      <div>
        <button type="submit" className={ui.primary} disabled={submitting}>
          {submitting ? t("submitting") : t("submit")}
        </button>
      </div>
    </form>
  );
}
