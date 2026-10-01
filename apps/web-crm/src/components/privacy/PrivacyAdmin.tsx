"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type DeletionProfile = {
  id: string;
  data_type: string;
  retention_months: number;
  start_rule: string;
  basis_note: string | null;
  released: boolean;
  released_at: string | null;
};
export type ErasureRequest = {
  id: string;
  contact_id: string;
  status: string;
  received_on: string;
  reason: string | null;
  blockers: { code: string; detail: string }[];
  decided_at: string | null;
  executed_at: string | null;
};
export type RegisterEntry = {
  id: string;
  kind: string;
  name: string;
  purpose: string | null;
  avv_status: string;
  third_country: boolean;
  legal_review_status: string;
  active: boolean;
};
type RecordsDraft = { title: string; status: string; review_notice: string; markdown: string };
type ContactHit = { id: string; display_name: string };

const DATA_TYPES = ["contact", "portal_account", "communication", "ticket", "other"] as const;
const KINDS = ["processor", "sub_processor", "processing_activity", "responsibility"] as const;
const AVV = ["none", "requested", "confirmed", "not_required"] as const;

/**
 * Datenschutz im CRM (Abschnitt 16, S16-04, S16-05): Löschprofile mit Freigabe, Löschanträge
 * mit Sperrprüfung und Vier-Augen-Freigabe, Register der Auftragsverarbeiter und
 * Verarbeitungen, Verzeichnis als Entwurf zum Herunterladen. Das Backend prüft Rechte und
 * Sperren, die Schaltflächen blenden nur aus. Fristen und Profile sind Entwürfe des Betreibers.
 */
export function PrivacyAdmin({ canManage, canApprove }: { canManage: boolean; canApprove: boolean }) {
  const t = useTranslations("PrivacyAdmin");
  const [profiles, setProfiles] = useState<DeletionProfile[] | null>(null);
  const [requests, setRequests] = useState<ErasureRequest[] | null>(null);
  const [register, setRegister] = useState<RegisterEntry[] | null>(null);
  const [draft, setDraft] = useState<RecordsDraft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [profileForm, setProfileForm] = useState({ data_type: "contact", retention_months: "36", start_rule: "", basis_note: "" });
  const [regForm, setRegForm] = useState({ kind: "processor", name: "", purpose: "", avv_status: "none" });
  const [contactQuery, setContactQuery] = useState("");
  const [contactHits, setContactHits] = useState<ContactHit[]>([]);
  const [erasure, setErasure] = useState({ contact_id: "", received_on: "", reason: "" });

  const load = useCallback(async () => {
    const [p, r, g] = await Promise.all([
      bff<DeletionProfile[]>("/api/bff/privacy/deletion-profiles"),
      bff<ErasureRequest[]>("/api/bff/privacy/erasure-requests"),
      bff<RegisterEntry[]>("/api/bff/privacy/register"),
    ]);
    if (p.ok) setProfiles(p.data ?? []);
    else setError(p.message);
    if (r.ok) setRequests(r.data ?? []);
    if (g.ok) setRegister(g.data ?? []);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function run(call: () => Promise<{ ok: boolean; message?: string }>): Promise<boolean> {
    setBusy(true);
    setError(null);
    const res = await call();
    setBusy(false);
    if (!res.ok) {
      setError(res.message ?? t("error"));
      return false;
    }
    await load();
    return true;
  }

  async function saveProfile(e: React.FormEvent) {
    e.preventDefault();
    const months = Number.parseInt(profileForm.retention_months, 10);
    if (!Number.isFinite(months) || months < 0 || !profileForm.start_rule.trim()) {
      setError(t("profileInvalid"));
      return;
    }
    await run(() =>
      bff("/api/bff/privacy/deletion-profiles", {
        method: "PUT",
        body: JSON.stringify({
          data_type: profileForm.data_type,
          retention_months: months,
          start_rule: profileForm.start_rule.trim(),
          basis_note: profileForm.basis_note.trim() || null,
        }),
      }),
    );
  }

  async function searchContacts() {
    const q = contactQuery.trim();
    if (q.length < 2) return;
    const res = await bff<{ items: ContactHit[] }>(`/api/bff/contacts?q=${encodeURIComponent(q)}&page_size=8`);
    if (res.ok) setContactHits(res.data?.items ?? []);
  }

  async function createErasure(e: React.FormEvent) {
    e.preventDefault();
    if (!erasure.contact_id || !erasure.received_on) {
      setError(t("erasureInvalid"));
      return;
    }
    const ok = await run(() =>
      bff("/api/bff/privacy/erasure-requests", {
        method: "POST",
        body: JSON.stringify({
          contact_id: erasure.contact_id,
          received_on: erasure.received_on,
          reason: erasure.reason.trim() || null,
        }),
      }),
    );
    if (ok) {
      setErasure({ contact_id: "", received_on: "", reason: "" });
      setContactHits([]);
      setContactQuery("");
    }
  }

  async function decide(id: string, action: "approve" | "reject" | "execute") {
    if (action === "execute" && !window.confirm(t("executeConfirm"))) return;
    await run(() => bff(`/api/bff/privacy/erasure-requests/${id}/${action}`, { method: "POST", body: JSON.stringify({}) }));
  }

  async function createRegister(e: React.FormEvent) {
    e.preventDefault();
    if (!regForm.name.trim()) return;
    const ok = await run(() =>
      bff("/api/bff/privacy/register", {
        method: "POST",
        body: JSON.stringify({ kind: regForm.kind, name: regForm.name.trim(), purpose: regForm.purpose.trim() || null, avv_status: regForm.avv_status }),
      }),
    );
    if (ok) setRegForm({ kind: "processor", name: "", purpose: "", avv_status: "none" });
  }

  async function loadDraft() {
    setBusy(true);
    const res = await bff<RecordsDraft>("/api/bff/privacy/processing-records");
    setBusy(false);
    if (res.ok) setDraft(res.data);
    else setError(res.message);
  }

  function download() {
    if (!draft) return;
    const blob = new Blob([draft.markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "verarbeitungsverzeichnis-entwurf.md";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex min-w-0 flex-col gap-6" data-testid="privacy-admin">
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}

      <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="privacy-profiles-title">
        <h2 id="privacy-profiles-title" className={ui.h2}>
          {t("profiles.title")}
        </h2>
        <p className={ui.help}>{t("profiles.intro")}</p>
        {profiles === null ? (
          <p className="text-sm text-muted">{t("loading")}</p>
        ) : profiles.length === 0 ? (
          <p className="text-sm text-muted">{t("profiles.empty")}</p>
        ) : (
          <div className={ui.tableScroll}>
            <table className={ui.table}>
              <thead>
                <tr>
                  <th>{t("profiles.dataType")}</th>
                  <th className="num">{t("profiles.months")}</th>
                  <th>{t("profiles.startRule")}</th>
                  <th>{t("profiles.status")}</th>
                  <th>{t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {profiles.map((p) => (
                  <tr key={p.id} data-testid="privacy-profile-row">
                    <td>{t(`dataType.${p.data_type}`)}</td>
                    <td className="num">{p.retention_months}</td>
                    <td>{p.start_rule}</td>
                    <td>{p.released ? t("profiles.released") : t("profiles.draft")}</td>
                    <td>
                      {!p.released && canApprove ? (
                        <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void run(() => bff(`/api/bff/privacy/deletion-profiles/${p.id}/release`, { method: "POST", body: JSON.stringify({}) }))}>
                          {t("profiles.release")}
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {canManage ? (
          <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => void saveProfile(e)} aria-label={t("profiles.formLabel")}>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("profiles.dataType")}</span>
              <select className={ui.input} value={profileForm.data_type} onChange={(e) => setProfileForm({ ...profileForm, data_type: e.target.value })}>
                {DATA_TYPES.map((d) => (
                  <option key={d} value={d}>
                    {t(`dataType.${d}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("profiles.months")}</span>
              <input className={ui.input} inputMode="numeric" value={profileForm.retention_months} onChange={(e) => setProfileForm({ ...profileForm, retention_months: e.target.value })} />
            </label>
            <label className="flex flex-col gap-1 sm:col-span-2">
              <span className={ui.label}>{t("profiles.startRule")}</span>
              <input className={ui.input} maxLength={200} value={profileForm.start_rule} onChange={(e) => setProfileForm({ ...profileForm, start_rule: e.target.value })} />
            </label>
            <label className="flex flex-col gap-1 sm:col-span-2">
              <span className={ui.label}>{t("profiles.basis")}</span>
              <input className={ui.input} value={profileForm.basis_note} onChange={(e) => setProfileForm({ ...profileForm, basis_note: e.target.value })} />
            </label>
            <div className="sm:col-span-2">
              <button type="submit" className={ui.primary} disabled={busy}>
                {t("profiles.save")}
              </button>
              <p className={`${ui.help} mt-1`}>{t("profiles.saveHint")}</p>
            </div>
          </form>
        ) : null}
      </section>

      <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="privacy-erasure-title">
        <h2 id="privacy-erasure-title" className={ui.h2}>
          {t("erasure.title")}
        </h2>
        <p className={ui.help}>{t("erasure.intro")}</p>
        {requests === null ? (
          <p className="text-sm text-muted">{t("loading")}</p>
        ) : requests.length === 0 ? (
          <p className="text-sm text-muted">{t("erasure.empty")}</p>
        ) : (
          <div className={ui.tableScroll}>
            <table className={ui.table}>
              <thead>
                <tr>
                  <th>{t("erasure.received")}</th>
                  <th>{t("erasure.contact")}</th>
                  <th>{t("erasure.status")}</th>
                  <th>{t("erasure.blockers")}</th>
                  <th>{t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {requests.map((r) => (
                  <tr key={r.id} data-testid="privacy-erasure-row">
                    <td>{new Date(`${r.received_on}T00:00:00`).toLocaleDateString("de-DE")}</td>
                    <td>
                      <a className="underline" href={`/kontakte/${r.contact_id}`}>
                        {t("erasure.openContact")}
                      </a>
                    </td>
                    <td>{t(`erasureStatus.${r.status}`)}</td>
                    <td>
                      {r.blockers.length === 0 ? (
                        t("erasure.noBlockers")
                      ) : (
                        <ul className="list-disc pl-4">
                          {r.blockers.map((b, i) => (
                            <li key={`${b.code}-${i}`}>{b.detail}</li>
                          ))}
                        </ul>
                      )}
                    </td>
                    <td className="flex flex-wrap gap-2">
                      {canApprove && r.status === "requested" ? (
                        <>
                          <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void decide(r.id, "approve")}>
                            {t("erasure.approve")}
                          </button>
                          <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void decide(r.id, "reject")}>
                            {t("erasure.reject")}
                          </button>
                        </>
                      ) : null}
                      {canApprove && r.status === "approved" ? (
                        <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void decide(r.id, "execute")}>
                          {t("erasure.execute")}
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {canManage ? (
          <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => void createErasure(e)} aria-label={t("erasure.formLabel")}>
            <div className="flex flex-col gap-1 sm:col-span-2">
              <label className={ui.label} htmlFor="privacy-contact-q">
                {t("erasure.contactSearch")}
              </label>
              <div className="flex gap-2">
                <input id="privacy-contact-q" className={ui.input} value={contactQuery} onChange={(e) => setContactQuery(e.target.value)} />
                <button type="button" className={ui.button} onClick={() => void searchContacts()}>
                  {t("erasure.search")}
                </button>
              </div>
              {contactHits.length > 0 ? (
                <select className={ui.input} aria-label={t("erasure.contact")} value={erasure.contact_id} onChange={(e) => setErasure({ ...erasure, contact_id: e.target.value })}>
                  <option value="">{t("erasure.choose")}</option>
                  {contactHits.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.display_name}
                    </option>
                  ))}
                </select>
              ) : null}
            </div>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("erasure.received")}</span>
              <input type="date" className={ui.input} value={erasure.received_on} onChange={(e) => setErasure({ ...erasure, received_on: e.target.value })} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("erasure.reason")}</span>
              <input className={ui.input} maxLength={1000} value={erasure.reason} onChange={(e) => setErasure({ ...erasure, reason: e.target.value })} />
            </label>
            <div className="sm:col-span-2">
              <button type="submit" className={ui.primary} disabled={busy}>
                {t("erasure.create")}
              </button>
            </div>
          </form>
        ) : null}
      </section>

      <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="privacy-register-title">
        <h2 id="privacy-register-title" className={ui.h2}>
          {t("register.title")}
        </h2>
        <p className={ui.help}>{t("register.intro")}</p>
        {register === null ? (
          <p className="text-sm text-muted">{t("loading")}</p>
        ) : register.length === 0 ? (
          <p className="text-sm text-muted">{t("register.empty")}</p>
        ) : (
          <div className={ui.tableScroll}>
            <table className={ui.table}>
              <thead>
                <tr>
                  <th>{t("register.name")}</th>
                  <th>{t("register.kind")}</th>
                  <th>{t("register.avv")}</th>
                  <th>{t("register.review")}</th>
                </tr>
              </thead>
              <tbody>
                {register.map((r) => (
                  <tr key={r.id} data-testid="privacy-register-row">
                    <td>{r.name}</td>
                    <td>{t(`kind.${r.kind}`)}</td>
                    <td>{t(`avv.${r.avv_status}`)}</td>
                    <td>{r.legal_review_status === "reviewed" ? t("register.reviewed") : t("register.reviewOpen")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {canManage ? (
          <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => void createRegister(e)} aria-label={t("register.formLabel")}>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("register.kind")}</span>
              <select className={ui.input} value={regForm.kind} onChange={(e) => setRegForm({ ...regForm, kind: e.target.value })}>
                {KINDS.map((k) => (
                  <option key={k} value={k}>
                    {t(`kind.${k}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("register.name")}</span>
              <input className={ui.input} maxLength={200} value={regForm.name} onChange={(e) => setRegForm({ ...regForm, name: e.target.value })} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("register.purpose")}</span>
              <input className={ui.input} value={regForm.purpose} onChange={(e) => setRegForm({ ...regForm, purpose: e.target.value })} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("register.avv")}</span>
              <select className={ui.input} value={regForm.avv_status} onChange={(e) => setRegForm({ ...regForm, avv_status: e.target.value })}>
                {AVV.map((a) => (
                  <option key={a} value={a}>
                    {t(`avv.${a}`)}
                  </option>
                ))}
              </select>
            </label>
            <div className="sm:col-span-2">
              <button type="submit" className={ui.primary} disabled={busy}>
                {t("register.create")}
              </button>
            </div>
          </form>
        ) : null}
      </section>

      <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="privacy-records-title">
        <h2 id="privacy-records-title" className={ui.h2}>
          {t("records.title")}
        </h2>
        <p className={ui.help}>{t("records.intro")}</p>
        <div className="flex flex-wrap gap-2">
          <button type="button" className={ui.button} disabled={busy} onClick={() => void loadDraft()}>
            {t("records.generate")}
          </button>
          {draft ? (
            <button type="button" className={ui.primary} onClick={download}>
              {t("records.download")}
            </button>
          ) : null}
        </div>
        {draft ? (
          <>
            <p className={ui.notice}>{draft.review_notice}</p>
            <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-md border border-border bg-surface-2 p-3 text-xs" data-testid="privacy-records-draft">
              {draft.markdown}
            </pre>
          </>
        ) : null}
      </section>
    </div>
  );
}
