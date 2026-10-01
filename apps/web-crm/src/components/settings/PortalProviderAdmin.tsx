"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { ContactPicker, type PickedContact } from "@/components/hoa/ContactPicker";
import { bff } from "@/lib/bff";
import { formatDate, formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type ProviderWindow = {
  id: string;
  provider_contact_id: string;
  starts_at: string;
  ends_at: string;
  kind: "available" | "unavailable";
  note: string | null;
};
type ProviderAccount = { id: string; email: string; status: string };
export type ClassGrant = {
  id: string;
  legal_entity_id: string;
  document_class: string;
  role: string;
  valid_from: string;
  valid_to: string | null;
};
export type EntityOption = { id: string; name: string };

const ROLES = ["provider", "tenant", "owner", "board"] as const;

/** Portal des Dienstleisters pflegen (GA11-04, AB12): Verfügbarkeitsfenster (Zeitfenster) und
 *  Freigaben je Unterlagenklasse. Die Prüfungen liegen im Backend; Bewertungen werden hier
 *  nicht angezeigt (Entscheidung AA14-02 offen). */
export function PortalProviderAdmin({
  canManage,
  legalEntities,
  documentClasses,
}: {
  canManage: boolean;
  legalEntities: EntityOption[];
  documentClasses: string[];
}) {
  const t = useTranslations("PortalProviders");
  const [contact, setContact] = useState<PickedContact | null>(null);
  const [windows, setWindows] = useState<ProviderWindow[]>([]);
  const [accounts, setAccounts] = useState<ProviderAccount[]>([]);
  const [grants, setGrants] = useState<ClassGrant[]>([]);
  const [accountId, setAccountId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [kind, setKind] = useState<"available" | "unavailable">("available");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [note, setNote] = useState("");

  const [entityId, setEntityId] = useState("");
  const [docClass, setDocClass] = useState("");
  const [role, setRole] = useState<string>("provider");
  const [validFrom, setValidFrom] = useState("");
  const [validTo, setValidTo] = useState("");

  async function loadGrants(id: string) {
    if (!id) {
      setGrants([]);
      return;
    }
    const res = await bff<ClassGrant[]>(`/api/bff/portal-admin/accounts/${id}/document-class-grants`);
    if (res.ok) setGrants(res.data);
    else setError(res.message);
  }

  async function pick(picked: PickedContact) {
    setContact(picked);
    setError(null);
    setLoading(true);
    const [win, acc] = await Promise.all([
      bff<ProviderWindow[]>(`/api/bff/portal-admin/provider-availability?provider_contact_id=${picked.id}`),
      bff<ProviderAccount[]>(`/api/bff/portal-admin/accounts?contact_id=${picked.id}`),
    ]);
    setLoading(false);
    if (!win.ok) return setError(win.message);
    setWindows(win.data);
    const list = acc.ok ? acc.data : [];
    setAccounts(list);
    const first = list[0]?.id ?? "";
    setAccountId(first);
    await loadGrants(first);
  }

  async function addWindow(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!contact) return;
    if (!startsAt || !endsAt) return setError(t("window.required"));
    const start = new Date(startsAt);
    const end = new Date(endsAt);
    if (end.getTime() <= start.getTime()) return setError(t("window.order"));
    const res = await bff<ProviderWindow>("/api/bff/portal-admin/provider-availability", {
      method: "POST",
      body: JSON.stringify({
        provider_contact_id: contact.id,
        starts_at: start.toISOString(),
        ends_at: end.toISOString(),
        kind,
        ...(note.trim() ? { note: note.trim() } : {}),
      }),
    });
    if (!res.ok) return setError(res.message);
    setWindows((rows) => [...rows, res.data].sort((a, b) => a.starts_at.localeCompare(b.starts_at)));
    setStartsAt("");
    setEndsAt("");
    setNote("");
  }

  async function removeWindow(id: string) {
    setError(null);
    const res = await bff<null>(`/api/bff/portal-admin/provider-availability/${id}`, { method: "DELETE" });
    if (!res.ok) return setError(res.message);
    setWindows((rows) => rows.filter((w) => w.id !== id));
  }

  async function addGrant(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!accountId || !entityId || !docClass) return setError(t("grants.required"));
    const res = await bff<ClassGrant>(`/api/bff/portal-admin/accounts/${accountId}/document-class-grants`, {
      method: "POST",
      body: JSON.stringify({
        legal_entity_id: entityId,
        document_class: docClass,
        role,
        ...(validFrom ? { valid_from: validFrom } : {}),
        ...(validTo ? { valid_to: validTo } : {}),
      }),
    });
    if (!res.ok) return setError(res.message);
    setGrants((rows) => [...rows, res.data]);
  }

  const entityName = (id: string) => legalEntities.find((e) => e.id === id)?.name ?? id;

  return (
    <div className="flex flex-col gap-4" data-testid="portal-provider-admin">
      <section className={ui.card}>
        <p className={ui.help}>{t("intro")}</p>
        <ContactPicker label={t("pickProvider")} onPick={(c) => void pick(c)} />
      </section>
      {error ? (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      ) : null}
      {contact ? (
        <>
          <section className={ui.card} aria-labelledby="pp-windows">
            <h2 id="pp-windows" className={ui.title}>
              {t("window.heading", { name: contact.display_name })}
            </h2>
            {loading ? <p className={ui.help}>{t("loading")}</p> : null}
            {windows.length === 0 && !loading ? <p className={ui.help}>{t("window.none")}</p> : null}
            <ul className="flex flex-col gap-1" data-testid="provider-windows">
              {windows.map((w) => (
                <li key={w.id} className="flex flex-wrap items-center gap-2">
                  <span>
                    {formatDateTime(w.starts_at)} bis {formatDateTime(w.ends_at)}, {t(`window.kind.${w.kind}`)}
                    {w.note ? `, ${w.note}` : ""}
                  </span>
                  {canManage ? (
                    <button type="button" className={ui.buttonSm} onClick={() => void removeWindow(w.id)}>
                      {t("window.remove")}
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
            {canManage ? (
              <form onSubmit={addWindow} noValidate className="mt-3 grid gap-2 sm:grid-cols-2" aria-label={t("window.add")}>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("window.start")}</span>
                  <input type="datetime-local" className={ui.input} value={startsAt} onChange={(e) => setStartsAt(e.target.value)} />
                </label>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("window.end")}</span>
                  <input type="datetime-local" className={ui.input} value={endsAt} onChange={(e) => setEndsAt(e.target.value)} />
                </label>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("window.kindLabel")}</span>
                  <select className={ui.input} value={kind} onChange={(e) => setKind(e.target.value as "available" | "unavailable")}>
                    <option value="available">{t("window.kind.available")}</option>
                    <option value="unavailable">{t("window.kind.unavailable")}</option>
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("window.note")}</span>
                  <input className={ui.input} maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
                </label>
                <div className="sm:col-span-2">
                  <button type="submit" className={ui.primary}>
                    {t("window.add")}
                  </button>
                </div>
              </form>
            ) : null}
          </section>

          <section className={ui.card} aria-labelledby="pp-grants">
            <h2 id="pp-grants" className={ui.title}>
              {t("grants.heading")}
            </h2>
            {accounts.length === 0 ? (
              <p className={ui.help}>{t("grants.noAccount")}</p>
            ) : (
              <>
                {accounts.length > 1 ? (
                  <label className="flex flex-col gap-1">
                    <span className={ui.label}>{t("grants.account")}</span>
                    <select
                      className={ui.input}
                      value={accountId}
                      onChange={(e) => {
                        setAccountId(e.target.value);
                        void loadGrants(e.target.value);
                      }}
                    >
                      {accounts.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.email}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
                {grants.length === 0 ? <p className={ui.help}>{t("grants.none")}</p> : null}
                <ul className="flex flex-col gap-1" data-testid="class-grants">
                  {grants.map((g) => (
                    <li key={g.id}>
                      {g.document_class}, {entityName(g.legal_entity_id)}, {t(`grants.role.${g.role}`)}, {formatDate(g.valid_from)}
                      {g.valid_to ? ` bis ${formatDate(g.valid_to)}` : ""}
                    </li>
                  ))}
                </ul>
                {canManage ? (
                  <form onSubmit={addGrant} noValidate className="mt-3 grid gap-2 sm:grid-cols-2" aria-label={t("grants.add")}>
                    <label className="flex flex-col gap-1">
                      <span className={ui.label}>{t("grants.entity")}</span>
                      <select className={ui.input} value={entityId} onChange={(e) => setEntityId(e.target.value)}>
                        <option value="">{t("grants.choose")}</option>
                        {legalEntities.map((e) => (
                          <option key={e.id} value={e.id}>
                            {e.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="flex flex-col gap-1">
                      <span className={ui.label}>{t("grants.class")}</span>
                      <select className={ui.input} value={docClass} onChange={(e) => setDocClass(e.target.value)}>
                        <option value="">{t("grants.choose")}</option>
                        {documentClasses.map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="flex flex-col gap-1">
                      <span className={ui.label}>{t("grants.roleLabel")}</span>
                      <select className={ui.input} value={role} onChange={(e) => setRole(e.target.value)}>
                        {ROLES.map((r) => (
                          <option key={r} value={r}>
                            {t(`grants.role.${r}`)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="flex flex-col gap-1">
                      <span className={ui.label}>{t("grants.validFrom")}</span>
                      <input type="date" className={ui.input} value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
                    </label>
                    <label className="flex flex-col gap-1">
                      <span className={ui.label}>{t("grants.validTo")}</span>
                      <input type="date" className={ui.input} value={validTo} onChange={(e) => setValidTo(e.target.value)} />
                    </label>
                    <div className="sm:col-span-2">
                      <button type="submit" className={ui.primary}>
                        {t("grants.add")}
                      </button>
                    </div>
                  </form>
                ) : null}
              </>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
