"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ContactPicker, type PickedContact } from "@/components/hoa/ContactPicker";
import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type Account = { id: string; email: string; status: string };

export type Representation = {
  id: string;
  account_id: string;
  principal_contact_id: string;
  document_id: string;
  valid_from: string;
  valid_to: string | null;
  status: string;
  note: string | null;
  revoked_at: string | null;
  representative_contact_id: string | null;
  representative_email: string | null;
};

/** Powers of attorney in the portal (P13, M21-05): a portal account of this contact may see the
 *  owner view of another contact, read only and only within the period, with the signed power
 *  of attorney as a mandatory document. The panel lists both directions (this contact represents
 *  others, others represent this contact), creates a power of attorney (upload of the document
 *  linked to the represented contact, then POST /portal-admin/representations) and revokes it.
 *  Reading needs tickets:read, creating and revoking tenant_settings:update (checked by the API). */
export function PortalRepresentationsPanel({ contactId, canManage }: { contactId: string; canManage: boolean }) {
  const t = useTranslations("PortalRepresentations");
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [reps, setReps] = useState<Representation[] | null>(null);
  const [names, setNames] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [accountId, setAccountId] = useState("");
  const [principal, setPrincipal] = useState<PickedContact | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [validFrom, setValidFrom] = useState("");
  const [validTo, setValidTo] = useState("");
  const [note, setNote] = useState("");

  const load = useCallback(async () => {
    const [accountsRes, repsRes] = await Promise.all([
      bff<Account[]>(`/api/bff/portal-admin/accounts?contact_id=${encodeURIComponent(contactId)}`),
      bff<Representation[]>("/api/bff/portal-admin/representations"),
    ]);
    if (!accountsRes.ok) {
      setError(accountsRes.message);
      return;
    }
    if (!repsRes.ok) {
      setError(repsRes.message);
      return;
    }
    const own = new Set((accountsRes.data ?? []).map((a) => a.id));
    const relevant = (repsRes.data ?? []).filter((r) => own.has(r.account_id) || r.principal_contact_id === contactId);
    setAccounts(accountsRes.data ?? []);
    setReps(relevant);
    setAccountId((current) => current || accountsRes.data?.[0]?.id || "");
    // Names of the counterpart contacts (name only endpoint).
    const wanted = new Set<string>();
    for (const r of relevant) {
      if (r.principal_contact_id !== contactId) wanted.add(r.principal_contact_id);
      if (r.representative_contact_id && r.representative_contact_id !== contactId) wanted.add(r.representative_contact_id);
    }
    const entries = await Promise.all(
      [...wanted].map(async (id) => {
        const res = await bff<{ display_name: string }>(`/api/bff/contacts/${id}/name`);
        return [id, res.ok ? res.data.display_name : id] as const;
      }),
    );
    setNames(Object.fromEntries(entries));
  }, [contactId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!accountId || !principal || !file || !validFrom) {
      setError(t("incomplete"));
      return;
    }
    if (validTo && validTo < validFrom) {
      setError(t("orderInvalid"));
      return;
    }
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file, file.name);
    form.append("title", t("documentTitle", { name: principal.display_name }));
    form.append("links", JSON.stringify([{ entity_type: "contact", entity_id: principal.id, role: "evidence" }]));
    const uploaded = await bff<{ id: string }>("/api/bff/documents", { method: "POST", body: form });
    if (!uploaded.ok) {
      setBusy(false);
      setError(uploaded.message);
      return;
    }
    const res = await bff("/api/bff/portal-admin/representations", {
      method: "POST",
      body: JSON.stringify({
        account_id: accountId,
        principal_contact_id: principal.id,
        document_id: uploaded.data.id,
        valid_from: validFrom,
        valid_to: validTo || null,
        note: note.trim() || null,
      }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setPrincipal(null);
    setFile(null);
    setValidFrom("");
    setValidTo("");
    setNote("");
    await load();
  }

  async function revoke(rep: Representation) {
    if (!window.confirm(t("revokeConfirm"))) return;
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/portal-admin/representations/${rep.id}/revoke`, { method: "POST" });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    await load();
  }

  const person = (id: string | null, fallback: string | null) =>
    id && id !== contactId ? (
      <Link href={`/kontakte/${id}`} className="hover:underline">
        {names[id] ?? fallback ?? id}
      </Link>
    ) : (
      <span>{fallback ?? t("thisContact")}</span>
    );

  return (
    <section className="mt-6 flex flex-col gap-3" aria-labelledby="portal-representations-title" data-testid="portal-representations">
      <h2 id="portal-representations-title" className="text-sm font-semibold">
        {t("title")}
      </h2>
      <p className="text-xs text-muted">{t("hint")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {reps === null ? (
        !error ? <p className="text-sm text-muted">{t("loading")}</p> : null
      ) : reps.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {reps.map((r) => (
            <li key={r.id} className={`${ui.card} flex flex-wrap items-center gap-2 text-sm`} data-testid="representation-row">
              <span>
                {r.principal_contact_id === contactId
                  ? t("representedBy")
                  : t("represents")}{" "}
                {r.principal_contact_id === contactId
                  ? person(r.representative_contact_id, r.representative_email)
                  : person(r.principal_contact_id, null)}
              </span>
              <span className="text-xs text-muted">
                {formatDate(r.valid_from)} {t("to")} {r.valid_to ? formatDate(r.valid_to) : t("open")}
              </span>
              <span className={r.status === "active" ? ui.badgeSuccess : ui.badge}>{t(`status.${r.status === "active" ? "active" : "revoked"}`)}</span>
              {r.note ? <span className="text-xs text-muted">{r.note}</span> : null}
              {canManage && r.status === "active" ? (
                <button type="button" className={`${ui.buttonSm} ml-auto`} disabled={busy} onClick={() => void revoke(r)}>
                  {t("revoke")}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {canManage && accounts !== null ? (
        accounts.length === 0 ? (
          <p className="text-sm text-muted">{t("noAccount")}</p>
        ) : (
          <form onSubmit={create} className={`${ui.card} flex flex-col gap-3`} aria-label={t("newTitle")}>
            <h3 className="text-sm font-semibold">{t("newTitle")}</h3>
            {accounts.length > 1 ? (
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("account")}</span>
                <select className={ui.input} value={accountId} onChange={(e) => setAccountId(e.target.value)}>
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.email}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            <ContactPicker label={t("principal")} onPick={setPrincipal} />
            {principal ? <p className="text-sm">{t("principalChosen", { name: principal.display_name })}</p> : null}
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("document")}</span>
              <input
                type="file"
                accept="application/pdf,image/jpeg,image/png"
                className={ui.input}
                data-testid="representation-document"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              <span className={ui.help}>{t("documentHint")}</span>
            </label>
            <div className="flex flex-wrap gap-3">
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("validFrom")}</span>
                <input type="date" className={ui.input} value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
              </label>
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("validTo")}</span>
                <input type="date" className={ui.input} value={validTo} onChange={(e) => setValidTo(e.target.value)} />
              </label>
            </div>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("note")}</span>
              <input className={ui.input} value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
            </label>
            <div className={ui.formActions}>
              <button type="submit" className={ui.primary} disabled={busy}>
                {t("create")}
              </button>
            </div>
          </form>
        )
      ) : null}
    </section>
  );
}
