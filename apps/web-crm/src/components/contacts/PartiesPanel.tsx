"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ContactPicker, type PickedContact } from "@/components/hoa/ContactPicker";
import { bff } from "@/lib/bff";
import { sumShares } from "@/lib/money";
import { ui } from "@/lib/ui";

export const PARTY_ROLES = ["primary", "co_party", "guarantor", "legal_representative"] as const;
export type PartyRole = (typeof PARTY_ROLES)[number];

export type PartyMember = {
  contact_id: string;
  role: PartyRole;
  share_percent: string | null;
  display_name: string;
};
export type Party = { id: string; name: string; members: PartyMember[] };

type Draft = { name: string; members: PartyMember[] };

/** Shares are sent as decimal strings (NUMERIC(20,8) in the API); an empty field means none. */
function shareValue(value: string | null): string | null {
  const text = (value ?? "").trim().replace(",", ".");
  return text === "" ? null : text;
}

function shareSum(members: PartyMember[]): number {
  return sumShares(members.map((m) => shareValue(m.share_percent)));
}

/** Contracting parties of a contact (M3-01, 6.1 party and party_member): list, create, edit
 *  name, members, roles and shares, delete. A party in use (contracts, owners, receivables) is
 *  refused by the API; the message is shown. Reading needs contacts:read, changes need
 *  contacts:update, creating contacts:create, deleting contacts:delete (checked by the API). */
export function PartiesPanel({
  contactId,
  contactName,
  canCreate,
  canUpdate,
  canDelete,
}: {
  contactId: string;
  contactName: string;
  canCreate: boolean;
  canUpdate: boolean;
  canDelete: boolean;
}) {
  const t = useTranslations("ContactParties");
  const [parties, setParties] = useState<Party[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    const res = await bff<Party[]>(`/api/bff/parties?contact_id=${encodeURIComponent(contactId)}`);
    if (res.ok) setParties(res.data ?? []);
    else setError(res.message);
  }, [contactId]);

  useEffect(() => {
    void load();
  }, [load]);

  function startEdit(party: Party) {
    setEditing(party.id);
    setCreating(false);
    setDraft({ name: party.name, members: party.members.map((m) => ({ ...m })) });
    setError(null);
  }

  function startCreate() {
    setCreating(true);
    setEditing(null);
    setDraft({
      name: "",
      members: [{ contact_id: contactId, role: "primary", share_percent: null, display_name: contactName }],
    });
    setError(null);
  }

  function cancel() {
    setEditing(null);
    setCreating(false);
    setDraft(null);
  }

  function setMember(index: number, patch: Partial<PartyMember>) {
    setDraft((d) => (d ? { ...d, members: d.members.map((m, i) => (i === index ? { ...m, ...patch } : m)) } : d));
  }

  function addMember(contact: PickedContact) {
    setDraft((d) => {
      if (!d || d.members.some((m) => m.contact_id === contact.id)) return d;
      return {
        ...d,
        members: [
          ...d.members,
          { contact_id: contact.id, role: "co_party", share_percent: null, display_name: contact.display_name },
        ],
      };
    });
  }

  function removeMember(index: number) {
    setDraft((d) => (d && d.members.length > 1 ? { ...d, members: d.members.filter((_, i) => i !== index) } : d));
  }

  function validate(d: Draft): string | null {
    if (d.members.length === 0) return t("membersRequired");
    if (shareSum(d.members) > 100) return t("sharesTooHigh");
    return null;
  }

  async function save() {
    if (!draft) return;
    const problem = validate(draft);
    if (problem) {
      setError(problem);
      return;
    }
    const members = draft.members.map((m) => ({
      contact_id: m.contact_id,
      role: m.role,
      share_percent: shareValue(m.share_percent),
    }));
    setBusy(true);
    setError(null);
    const res = creating
      ? await bff<Party>("/api/bff/parties", {
          method: "POST",
          body: JSON.stringify({ name: draft.name.trim() || null, members }),
        })
      : await bff<Party>(`/api/bff/parties/${editing}`, {
          method: "PATCH",
          body: JSON.stringify({ name: draft.name.trim() || undefined, members }),
        });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    cancel();
    await load();
  }

  async function remove(party: Party) {
    if (!window.confirm(t("deleteConfirm", { name: party.name }))) return;
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/parties/${party.id}`, { method: "DELETE" });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    await load();
  }

  const form = draft ? (
    <form
      className={`${ui.card} flex flex-col gap-3`}
      aria-label={creating ? t("newTitle") : t("editTitle")}
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <h3 className="text-sm font-semibold">{creating ? t("newTitle") : t("editTitle")}</h3>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("name")}</span>
        <input
          className={ui.input}
          value={draft.name}
          maxLength={400}
          placeholder={t("namePlaceholder")}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })}
        />
        <span className={ui.help}>{t("nameHint")}</span>
      </label>
      <ul className="flex flex-col gap-2" data-testid="party-draft-members">
        {draft.members.map((m, index) => (
          <li key={m.contact_id} className="flex flex-wrap items-end gap-2 text-sm">
            <span className="min-w-40 flex-1 font-medium">{m.display_name}</span>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("role")}</span>
              <select
                className={ui.input}
                value={m.role}
                aria-label={t("roleFor", { name: m.display_name })}
                onChange={(e) => setMember(index, { role: e.target.value as PartyRole })}
              >
                {PARTY_ROLES.map((r) => (
                  <option key={r} value={r}>
                    {t(`roles.${r}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("share")}</span>
              <input
                className={`${ui.input} w-28`}
                inputMode="decimal"
                value={m.share_percent ?? ""}
                aria-label={t("shareFor", { name: m.display_name })}
                onChange={(e) => setMember(index, { share_percent: e.target.value })}
              />
            </label>
            <button
              type="button"
              className={ui.buttonSm}
              disabled={draft.members.length <= 1}
              aria-label={t("removeMember", { name: m.display_name })}
              onClick={() => removeMember(index)}
            >
              {t("remove")}
            </button>
          </li>
        ))}
      </ul>
      <ContactPicker label={t("addMember")} onPick={addMember} />
      <p className={ui.help}>{t("shareSum", { sum: shareSum(draft.members).toLocaleString("de-DE", { maximumFractionDigits: 8 }) })}</p>
      <div className={ui.formActions}>
        <button type="submit" className={ui.primary} disabled={busy}>
          {t("save")}
        </button>
        <button type="button" className={ui.secondary} onClick={cancel}>
          {t("cancel")}
        </button>
      </div>
    </form>
  ) : null;

  return (
    <section className="mt-6 flex flex-col gap-3" aria-labelledby="contact-parties-title" data-testid="contact-parties">
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="contact-parties-title" className="text-sm font-semibold">
          {t("title")}
        </h2>
        {canCreate && !creating ? (
          <button type="button" className={`${ui.buttonSm} ml-auto`} onClick={startCreate}>
            {t("new")}
          </button>
        ) : null}
      </div>
      <p className="text-xs text-muted">{t("hint")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {creating ? form : null}
      {parties === null ? (
        <p className="text-sm text-muted">{t("loading")}</p>
      ) : parties.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {parties.map((party) =>
            editing === party.id ? (
              <li key={party.id}>{form}</li>
            ) : (
              <li key={party.id} className={`${ui.card} flex flex-col gap-2 text-sm`} data-testid="party-row">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{party.name}</span>
                  <span className="ml-auto flex gap-2">
                    {canUpdate ? (
                      <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => startEdit(party)}>
                        {t("edit")}
                      </button>
                    ) : null}
                    {canDelete ? (
                      <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void remove(party)}>
                        {t("delete")}
                      </button>
                    ) : null}
                  </span>
                </div>
                <ul className="flex flex-col gap-0.5">
                  {party.members.map((m) => (
                    <li key={m.contact_id} className="flex flex-wrap gap-2">
                      {m.contact_id === contactId ? (
                        <span>{m.display_name}</span>
                      ) : (
                        <Link href={`/kontakte/${m.contact_id}`} className="hover:underline">
                          {m.display_name}
                        </Link>
                      )}
                      <span className="text-xs text-muted">
                        {t(`roles.${m.role}`)}
                        {m.share_percent !== null && m.share_percent !== ""
                          ? `, ${t("shareValue", { value: Number.parseFloat(m.share_percent).toLocaleString("de-DE", { maximumFractionDigits: 8 }) })}`
                          : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              </li>
            ),
          )}
        </ul>
      )}
    </section>
  );
}
