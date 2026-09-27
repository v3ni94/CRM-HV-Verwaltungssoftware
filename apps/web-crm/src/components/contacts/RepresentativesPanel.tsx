"use client";

import type { components } from "@mhvp/api-client";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ContactPicker, type PickedContact } from "@/components/hoa/ContactPicker";
import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export type ContactRelation = components["schemas"]["RelationOut"];
export type DeliveryMode = components["schemas"]["DeliveryMode"];
const MODES: DeliveryMode[] = ["both", "representative_only", "owner_only"];

function period(r: ContactRelation, t: (key: string, values?: Record<string, string>) => string): string {
  const from = formatDate(r.valid_from);
  const to = formatDate(r.valid_to);
  if (from && to) return `${from} bis ${to}`;
  if (from) return t("since", { date: from });
  if (to) return t("until", { date: to });
  return t("unlimited");
}

/** Authorised representatives of a contact with their delivery rule (operator decision
 *  26.09.2026): who receives mails, letters and WEG invitations addressed to this contact.
 *  Staff with contacts:update change the rule or end the authorisation; every change is
 *  audited by the API. Incoming rows show whom this contact represents. */
export function RepresentativesPanel({
  contactId,
  relations,
  canEdit,
}: {
  contactId: string;
  relations: ContactRelation[];
  canEdit: boolean;
}) {
  const t = useTranslations("Contacts.representatives");
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [picked, setPicked] = useState<PickedContact | null>(null);
  const [mode, setMode] = useState<DeliveryMode>("both");

  const representatives = relations.filter((r) => r.kind === "representative" && r.direction === "outgoing");
  const represents = relations.filter((r) => r.kind === "representative" && r.direction === "incoming");

  async function run(call: () => Promise<{ ok: boolean; message?: string }>) {
    setError(null);
    setBusy(true);
    const result = await call();
    setBusy(false);
    if (!result.ok) {
      setError(result.message ?? t("error"));
      return;
    }
    router.refresh();
  }

  function changeMode(relation: ContactRelation, next: DeliveryMode) {
    void run(() =>
      bff(`/api/bff/contacts/${contactId}/contact-relations/${relation.id}`, {
        method: "PATCH",
        body: JSON.stringify({ delivery_mode: next, fields: ["delivery_mode"] }),
      }),
    );
  }

  function end(relation: ContactRelation) {
    if (!window.confirm(t("endConfirm", { name: relation.related_display_name ?? "" }))) return;
    void run(() => bff(`/api/bff/contacts/${contactId}/contact-relations/${relation.id}`, { method: "DELETE" }));
  }

  function add(event: React.FormEvent) {
    event.preventDefault();
    if (!picked) return;
    const contact = picked;
    void run(async () => {
      const result = await bff(`/api/bff/contacts/${contactId}/relations`, {
        method: "POST",
        body: JSON.stringify({ related_contact_id: contact.id, kind: "representative", delivery_mode: mode }),
      });
      if (result.ok) setPicked(null);
      return result;
    });
  }

  return (
    <section className="mt-6 flex flex-col gap-3" aria-labelledby="contact-representatives-title">
      <h2 id="contact-representatives-title" className="text-sm font-semibold">
        {t("title")}
      </h2>
      <p className="text-xs text-muted">{t("hint")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {representatives.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {representatives.map((r) => (
            <li key={r.id} className={`${ui.card} flex flex-wrap items-center gap-3 text-sm`}>
              <Link href={`/kontakte/${r.related_contact_id}`} className="font-medium hover:underline">
                {r.related_display_name ?? r.related_contact_id}
              </Link>
              <span className="text-xs text-muted">{period(r, t)}</span>
              <label className="ml-auto flex items-center gap-2">
                <span className="text-xs text-muted">{t("mode")}</span>
                <select
                  className={ui.input}
                  value={r.delivery_mode}
                  disabled={!canEdit || busy}
                  aria-label={t("modeFor", { name: r.related_display_name ?? "" })}
                  onChange={(e) => changeMode(r, e.target.value as DeliveryMode)}
                >
                  {MODES.map((m) => (
                    <option key={m} value={m}>
                      {t(`modes.${m}`)}
                    </option>
                  ))}
                </select>
              </label>
              {canEdit ? (
                <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => end(r)}>
                  {t("end")}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {represents.length > 0 ? (
        <p className="text-sm">
          {t("represents")}{" "}
          {represents.map((r, i) => (
            <span key={r.id}>
              {i > 0 ? ", " : ""}
              <Link href={`/kontakte/${r.related_contact_id}`} className="hover:underline">
                {r.related_display_name ?? r.related_contact_id}
              </Link>{" "}
              <span className="text-xs text-muted">({t(`modes.${r.delivery_mode}`)})</span>
            </span>
          ))}
        </p>
      ) : null}
      {canEdit ? (
        <form onSubmit={add} className="flex flex-wrap items-end gap-3" aria-label={t("add")}>
          <div className="min-w-64 flex-1">
            <ContactPicker label={t("pick")} kind="person" onPick={setPicked} />
            {picked ? (
              <p className="mt-1 text-sm">
                {t("picked")}: <span className="font-medium">{picked.display_name}</span>
              </p>
            ) : null}
          </div>
          <div>
            <label htmlFor="representative-mode" className={ui.label}>
              {t("mode")}
            </label>
            <select id="representative-mode" className={ui.input} value={mode} onChange={(e) => setMode(e.target.value as DeliveryMode)}>
              {MODES.map((m) => (
                <option key={m} value={m}>
                  {t(`modes.${m}`)}
                </option>
              ))}
            </select>
          </div>
          <button type="submit" className={ui.primary} disabled={busy || !picked}>
            {t("save")}
          </button>
        </form>
      ) : null}
    </section>
  );
}
