"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";

import { BankAccountSelect } from "@/components/banking/BankAccountSelect";
import { StatusPill, type StatusPillVariant } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { formatDate, formatDateTime, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

import { INLINE_KINDS, ownersFor, type InlineKind } from "./BankSetupWizard";
import { DisconnectedToggle, isDisconnected, useShowDisconnected } from "./DisconnectedToggle";

export type FinTsInstitute = {
  blz: string;
  name: string;
  city: string;
  bic: string | null;
  fints_url: string | null;
  connectable: boolean;
};

export type FinTsTanMechanism = { code: string; name: string; decoupled: boolean };

export type FinTsSession = {
  id: string;
  fints_connection_id: string;
  purpose: string;
  status: "queued" | "running" | "awaiting_tan" | "awaiting_decoupled" | "done" | "failed";
  tan_mechanism: string | null;
  tan_mechanisms: FinTsTanMechanism[];
  challenge_text: string | null;
  challenge_hhduc: string | null;
  challenge_image_mime: string | null;
  challenge_image_base64: string | null;
  challenge_decoupled: boolean;
  tan_pending: boolean;
  error_code: string | null;
  error_message: string | null;
  result: Record<string, number | boolean>;
  sync_run_id: string | null;
};

export type FinTsAccount = {
  id: string;
  iban_suffix: string;
  bic: string | null;
  account_number: string | null;
  property_bank_account_id: string | null;
  balance_booked: string | null;
  balance_currency: string | null;
  balance_as_of: string | null;
  balance_fetched_at: string | null;
  last_transactions_fetch_at: string | null;
  last_synced_booking_date: string | null;
};

export type FinTsConnection = {
  id: string;
  bank_connection_id: string;
  bank_name: string;
  blz: string;
  bic: string | null;
  /** Address a dialog uses now; the manual entry (if any) and the institute list entry. */
  fints_url?: string;
  fints_url_manual?: string | null;
  fints_url_list?: string | null;
  status: string;
  tan_mechanism: string | null;
  tan_mechanisms: FinTsTanMechanism[];
  last_sca_at: string | null;
  sca_due: boolean;
  sca_due_on: string | null;
  pin_blocked: boolean;
  last_error: string | null;
  last_error_code: string | null;
  last_sync_at: string | null;
  open_session_id: string | null;
  accounts: FinTsAccount[];
};

/** Codes whose message carries numbered check steps (locked access, bank not reachable). */
const CHECK_STEP_CODES = ["MHVP-BANK-0010", "MHVP-BANK-0013"];

function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

const STATUS_VARIANT: Record<string, StatusPillVariant> = {
  not_configured: "neutral",
  web_form_pending: "warning",
  active: "success",
  update_required: "warning",
  error: "danger",
  consent_expired: "warning",
  disabled: "neutral",
};

const POLL_MS = 2000;
const DECOUPLED_POLL_MS = 5000;

/** TAN-Schritt einer FinTS-Sitzung: fragt den Stand ab, zeigt die Challenge (Text, HHD-Code,
 *  Bild bei photoTAN), nimmt die TAN entgegen oder fragt bei pushTAN die Freigabe ab. */
export function FinTsSessionPanel({
  sessionId,
  onDone,
  onFailed,
}: {
  sessionId: string;
  onDone?: (session: FinTsSession) => void;
  onFailed?: (session: FinTsSession) => void;
}) {
  const t = useTranslations("FinTs");
  const [session, setSession] = useState<FinTsSession | null>(null);
  const [tan, setTan] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const finishedRef = useRef(false);

  const load = useCallback(async () => {
    const result = await bff<FinTsSession>(`/api/bff/banking/fints/sessions/${sessionId}`);
    if (!result.ok) {
      setError(result.message);
      return null;
    }
    setSession(result.data);
    return result.data;
  }, [sessionId]);

  const poll = useCallback(async () => {
    setBusy(true);
    setError(null);
    const result = await bff<FinTsSession>(`/api/bff/banking/fints/sessions/${sessionId}/tan`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    setBusy(false);
    if (!result.ok) setError(result.message);
    await load();
  }, [sessionId, load]);

  useEffect(() => {
    finishedRef.current = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;
    const tick = async () => {
      const current = await load();
      if (cancelled || !current) return;
      if (current.status === "done" || current.status === "failed") {
        if (!finishedRef.current) {
          finishedRef.current = true;
          if (current.status === "done") onDone?.(current);
          else onFailed?.(current);
        }
        return;
      }
      if (current.status === "awaiting_decoupled" && !current.tan_pending) {
        timer = setTimeout(async () => {
          await poll();
          if (!cancelled) timer = setTimeout(tick, POLL_MS);
        }, DECOUPLED_POLL_MS);
        return;
      }
      if (current.status === "awaiting_tan" && !current.tan_pending) return;
      timer = setTimeout(tick, POLL_MS);
    };
    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  async function submitTan() {
    if (!session) return;
    setBusy(true);
    setError(null);
    const result = await bff<FinTsSession>(`/api/bff/banking/fints/sessions/${session.id}/tan`, {
      method: "POST",
      body: JSON.stringify({ tan }),
    });
    setBusy(false);
    setTan("");
    if (!result.ok) {
      setError(result.message);
      return;
    }
    // resume polling until the worker has processed the TAN
    const wait = async () => {
      const current = await load();
      if (!current) return;
      if (current.status === "done") {
        if (!finishedRef.current) {
          finishedRef.current = true;
          onDone?.(current);
        }
      } else if (current.status === "failed") {
        if (!finishedRef.current) {
          finishedRef.current = true;
          onFailed?.(current);
        }
      } else if (current.tan_pending || current.status === "running" || current.status === "queued") {
        setTimeout(wait, POLL_MS);
      }
    };
    setTimeout(wait, POLL_MS);
  }

  if (!session) {
    return <p className="text-sm text-muted">{error ?? t("sessionLoading")}</p>;
  }
  const mechanism = session.tan_mechanisms.find((m) => m.code === session.tan_mechanism);
  return (
    <div className="flex flex-col gap-2" data-testid="fints-session">
      <p className="text-sm">
        <span className="font-medium">{t(`sessionStatus.${session.status}`)}</span>
        {mechanism ? <span className="ml-2 text-xs text-muted">{t("tanMechanism")}: {mechanism.name}</span> : null}
      </p>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      {(session.status === "queued" || session.status === "running" || session.tan_pending) ? (
        <p className={ui.notice}>{t("sessionWorking")}</p>
      ) : null}
      {session.status === "awaiting_tan" && !session.tan_pending ? (
        <div className="flex flex-col gap-2">
          {session.challenge_text ? <p className={ui.notice}>{session.challenge_text}</p> : null}
          {session.challenge_image_base64 ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              alt={t("challengeImage")}
              className="max-w-xs rounded border border-border"
              src={`data:${session.challenge_image_mime ?? "image/png"};base64,${session.challenge_image_base64}`}
            />
          ) : null}
          {session.challenge_hhduc ? (
            <p className="text-xs text-muted">
              {t("challengeHhduc")}: <span className={ui.mono}>{session.challenge_hhduc}</span>
            </p>
          ) : null}
          <label className="flex flex-col gap-1 text-sm">
            {t("tan")}
            <input
              className={ui.input}
              autoComplete="one-time-code"
              inputMode="numeric"
              value={tan}
              onChange={(e) => setTan(e.target.value)}
              aria-label={t("tan")}
            />
          </label>
          <button type="button" className={ui.primary} disabled={busy || !tan} onClick={submitTan}>
            {t("submitTan")}
          </button>
        </div>
      ) : null}
      {session.status === "awaiting_decoupled" && !session.tan_pending ? (
        <div className="flex flex-col gap-2">
          <p className={ui.notice}>{session.challenge_text ?? t("decoupledHint")}</p>
          <p className="text-xs text-muted">{t("decoupledPolling")}</p>
          <button type="button" className={ui.buttonSm} disabled={busy} onClick={poll}>
            {t("checkDecoupled")}
          </button>
        </div>
      ) : null}
      {session.status === "failed" ? (
        <p role="alert" className={ui.alert}>
          <span className="block whitespace-pre-line">{session.error_message ?? t("sessionFailed")}</span>
          {session.error_code ? <span className="text-xs">({session.error_code})</span> : null}
          {session.error_code === "MHVP-BANK-0009" || session.error_code === "MHVP-BANK-0016" ? (
            <span className="block text-xs">{t("pinLockHint")}</span>
          ) : null}
          {session.error_code && CHECK_STEP_CODES.includes(session.error_code) ? (
            <span className="block text-xs">{t("handbookHint")}</span>
          ) : null}
        </p>
      ) : null}
      {session.status === "done" ? <p className={ui.success}>{t("sessionDone")}</p> : null}
    </div>
  );
}

function InstituteSearch({ onSelect }: { onSelect: (inst: FinTsInstitute) => void }) {
  const t = useTranslations("FinTs");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<FinTsInstitute[]>([]);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setHits([]);
      return;
    }
    let cancelled = false;
    setSearching(true);
    const timer = setTimeout(async () => {
      const result = await bff<FinTsInstitute[]>(`/api/bff/banking/fints/institutes?q=${encodeURIComponent(q)}`);
      if (cancelled) return;
      setSearching(false);
      setHits(result.ok ? result.data : []);
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query]);

  return (
    <div className="flex flex-col gap-2">
      <label className="flex flex-col gap-1 text-sm">
        {t("instituteQuery")}
        <input
          className={ui.input}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("instituteQueryPlaceholder")}
          aria-label={t("instituteQuery")}
        />
      </label>
      <p className={ui.help}>{t("instituteHelp")}</p>
      {searching ? <p className="text-xs text-muted">{t("searching")}</p> : null}
      {hits.length > 0 ? (
        <ul className="flex max-h-64 flex-col divide-y divide-border overflow-y-auto rounded border border-border" role="listbox">
          {hits.map((inst) => (
            <li key={inst.blz}>
              <button
                type="button"
                role="option"
                aria-selected={false}
                disabled={!inst.connectable}
                className="flex w-full flex-col items-start gap-0.5 px-3 py-2 text-left text-sm hover:bg-surface-2 disabled:opacity-60"
                onClick={() => onSelect(inst)}
              >
                <span className="font-medium">{inst.name}</span>
                <span className="text-xs text-muted">
                  {inst.city} · BLZ {inst.blz}
                  {inst.bic ? ` · ${inst.bic}` : ""}
                  {inst.connectable ? "" : ` · ${t("notConnectable")}`}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : query.trim().length >= 2 && !searching ? (
        <p className="text-xs text-muted">{t("noInstitutes")}</p>
      ) : null}
    </div>
  );
}

/** Dialog "Bank verbinden": Institut suchen, Zugangsdaten, TAN-Freigabe, Konten zuordnen. */
export function FinTsConnectDialog({ onClose, onChanged }: { onClose: () => void; onChanged: () => Promise<void> | void }) {
  const t = useTranslations("FinTs");
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);
  const [institute, setInstitute] = useState<FinTsInstitute | null>(null);
  const [login, setLogin] = useState("");
  const [pin, setPin] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<FinTsSession | null>(null);
  const [connection, setConnection] = useState<FinTsConnection | null>(null);

  async function connect() {
    if (!institute) return;
    setBusy(true);
    setError(null);
    const result = await bff<FinTsSession>("/api/bff/banking/fints/connections", {
      method: "POST",
      body: JSON.stringify({ institute: institute.blz, login, pin }),
    });
    setBusy(false);
    setPin("");
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setSession(result.data);
    setStep(3);
  }

  async function loadConnection(id: string) {
    const list = await bff<FinTsConnection[]>("/api/bff/banking/fints/connections");
    if (list.ok) setConnection(list.data.find((c) => c.id === id) ?? null);
  }

  async function retry() {
    if (!session) return;
    setBusy(true);
    setError(null);
    const result = await bff<FinTsSession>(`/api/bff/banking/fints/connections/${session.fints_connection_id}/restart`, {
      method: "POST",
      body: JSON.stringify(pin ? { pin } : {}),
    });
    setBusy(false);
    setPin("");
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setSession(result.data);
  }

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="fints-dialog-title" className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-scrim p-4">
      <div className={`${ui.card} mt-8 w-full max-w-xl`}>
        <div className="flex items-start justify-between gap-2">
          <h2 id="fints-dialog-title" className={ui.h2}>{t("connectTitle")}</h2>
          <button type="button" className={ui.buttonSm} onClick={onClose}>
            {t("close")}
          </button>
        </div>
        <ol className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
          {[1, 2, 3, 4].map((n) => (
            <li key={n} className={step === n ? "font-medium text-fg" : ""}>
              {t(`step${n}`)}
            </li>
          ))}
        </ol>
        {error ? <p role="alert" className={`${ui.alert} mt-2`}>{error}</p> : null}
        <div className="mt-3">
          {step === 1 ? (
            <InstituteSearch
              onSelect={(inst) => {
                setInstitute(inst);
                setStep(2);
              }}
            />
          ) : null}
          {step === 2 && institute ? (
            <form
              aria-label={t("connectTitle")}
              className="flex flex-col gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                connect();
              }}
            >
              <p className="text-sm">
                <span className="font-medium">{institute.name}</span>
                <span className="ml-1 text-xs text-muted">{institute.city} · BLZ {institute.blz}</span>
                <button type="button" className="ml-2 text-xs underline" onClick={() => setStep(1)}>
                  {t("changeInstitute")}
                </button>
              </p>
              <label className="flex flex-col gap-1 text-sm">
                {t("login")}
                <input className={ui.input} value={login} onChange={(e) => setLogin(e.target.value)} autoComplete="username" aria-label={t("login")} />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                {t("pin")}
                <input className={ui.input} type="password" value={pin} onChange={(e) => setPin(e.target.value)} autoComplete="current-password" aria-label={t("pin")} />
              </label>
              <p className={ui.help}>{t("pinHelp")}</p>
              <p className={ui.help}>{t("pinLockHint")}</p>
              <div className={ui.formActions}>
                <button type="submit" className={ui.primary} disabled={busy || !login || !pin}>
                  {t("startConnect")}
                </button>
              </div>
            </form>
          ) : null}
          {step === 3 && session ? (
            <div className="flex flex-col gap-3">
              <FinTsSessionPanel
                key={session.id}
                sessionId={session.id}
                onDone={async (done) => {
                  await loadConnection(done.fints_connection_id);
                  await onChanged();
                  setStep(4);
                }}
                onFailed={(failed) => setSession(failed)}
              />
              {session.status === "failed" ? (
                <div className="flex flex-col gap-2">
                  {session.error_code === "MHVP-BANK-0009" || session.error_code === "MHVP-BANK-0016" ? (
                    <label className="flex flex-col gap-1 text-sm">
                      {t("pinAgain")}
                      <input className={ui.input} type="password" value={pin} onChange={(e) => setPin(e.target.value)} aria-label={t("pinAgain")} />
                    </label>
                  ) : null}
                  <button type="button" className={ui.buttonSm} disabled={busy} onClick={retry}>
                    {t("retry")}
                  </button>
                </div>
              ) : null}
            </div>
          ) : null}
          {step === 4 && connection ? (
            <div className="flex flex-col gap-2">
              <p className={ui.success}>{t("accountsLoaded", { count: connection.accounts.length })}</p>
              <FinTsAccountTable connection={connection} onChanged={async () => {
                await loadConnection(connection.id);
                await onChanged();
              }} />
              <div className={ui.formActions}>
                <button type="button" className={ui.primary} onClick={onClose}>
                  {t("finish")}
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function FinTsAccountTable({ connection, onChanged }: { connection: FinTsConnection; onChanged: () => Promise<void> | void }) {
  const t = useTranslations("FinTs");
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState<string | null>(null);

  async function assign(linkId: string, accountId: string) {
    setError(null);
    const result = await bff(`/api/bff/banking/fints/accounts/${linkId}/assign`, {
      method: "POST",
      body: JSON.stringify({ property_bank_account_id: accountId }),
    });
    if (!result.ok) {
      setError(result.message);
      return;
    }
    await onChanged();
  }

  if (connection.accounts.length === 0) return <p className="text-sm text-muted">{t("noAccounts")}</p>;
  return (
    <div className="overflow-x-auto">
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      <table className="mhvp-table">
        <thead>
          <tr>
            <th>{t("account")}</th>
            <th className="num">{t("balance")}</th>
            <th>{t("assignment")}</th>
            <th>{t("lastFetch")}</th>
          </tr>
        </thead>
        <tbody>
          {connection.accounts.map((a) => (
            <tr key={a.id}>
              <td>
                <span className={ui.mono}>…{a.iban_suffix}</span>
                {a.bic ? <span className="ml-1 text-xs text-muted">{a.bic}</span> : null}
              </td>
              <td className="num">
                {a.balance_booked
                  ? formatEur(a.balance_booked) + (a.balance_currency && a.balance_currency !== "EUR" ? ` ${a.balance_currency}` : "")
                  : "–"}
                {a.balance_as_of ? <span className="ml-1 text-xs text-muted">{formatDate(a.balance_as_of)}</span> : null}
              </td>
              <td className="min-w-64">
                <BankAccountSelect
                  value={a.property_bank_account_id}
                  showBalance={false}
                  placeholder={t("assignPlaceholder")}
                  onChange={(opt) => {
                    if (opt) assign(a.id, opt.id);
                  }}
                />
                {!a.property_bank_account_id ? (
                  <>
                    <p className={ui.help}>{t("assignHelp")}</p>
                    <p className="mt-1 flex flex-wrap gap-2 text-sm" data-testid={`fints-unassigned-${a.id}`}>
                      <span>{t("noMatchHint")}</span>
                      <a className="text-accent underline" href={`/bank?setup=fints&link=${encodeURIComponent(a.id)}`}>{t("openWizard")}</a>
                      <button type="button" className={ui.buttonSm} onClick={() => setCreating(creating === a.id ? null : a.id)}>
                        {creating === a.id ? t("createCancel") : t("createInternal")}
                      </button>
                    </p>
                    {creating === a.id ? (
                      <FinTsCreateInternalForm
                        link={a}
                        defaultHolder=""
                        onDone={async () => {
                          setCreating(null);
                          await onChanged();
                        }}
                      />
                    ) : null}
                  </>
                ) : null}
              </td>
              <td className="text-xs text-muted">
                {a.last_transactions_fetch_at ? formatDateTime(a.last_transactions_fetch_at) : t("neverFetched")}
                {a.last_synced_booking_date ? <span className="block">{t("cursor")}: {formatDate(a.last_synced_booking_date)}</span> : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type FinTsPropertyOption = { id: string; number: string; name: string };
type FinTsEntityOption = { id: string; kind: string; name: string };

/** Inline "Internes Konto anlegen" (GAG-02): creates the internal account for the bank's IBAN
 *  via `POST /banking/fints/accounts/{id}/assign` with property, legal entity (owner kinds per
 *  ACCOUNT_OWNERS, 6.9.1), kind and holder. Read only towards the bank; no payment, no posting. */
export function FinTsCreateInternalForm({
  link,
  defaultHolder,
  onDone,
}: {
  link: FinTsAccount;
  defaultHolder: string;
  onDone: () => Promise<void> | void;
}) {
  const t = useTranslations("FinTs");
  const tk = useTranslations("BankAccounts.kind");
  const te = useTranslations("Properties.entityKind");
  const [properties, setProperties] = useState<FinTsPropertyOption[]>([]);
  const [propertyId, setPropertyId] = useState("");
  const [entities, setEntities] = useState<FinTsEntityOption[]>([]);
  const [kind, setKind] = useState<InlineKind>("hoa");
  const [legalEntityId, setLegalEntityId] = useState("");
  const [holder, setHolder] = useState(defaultHolder);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    bff<{ items: FinTsPropertyOption[] }>("/api/bff/properties?page_size=200").then((r) => {
      if (r.ok) setProperties(r.data.items);
    });
  }, []);
  useEffect(() => {
    if (!propertyId) {
      setEntities([]);
      return;
    }
    bff<FinTsEntityOption[]>(`/api/bff/properties/${propertyId}/legal-entities`).then((r) => setEntities(r.ok ? r.data : []));
  }, [propertyId]);
  const owners = useMemo(() => ownersFor(kind, entities), [kind, entities]);
  useEffect(() => {
    const first = owners[0];
    if (!first) {
      if (legalEntityId) setLegalEntityId("");
      return;
    }
    if (!owners.some((o) => o.id === legalEntityId)) setLegalEntityId(first.id);
  }, [owners, legalEntityId]);
  useEffect(() => {
    const entity = owners.find((o) => o.id === legalEntityId);
    if (entity && !holder) setHolder(entity.name);
  }, [owners, legalEntityId, holder]);

  const ready = Boolean(propertyId && legalEntityId && holder.trim().length >= 2);

  async function submit() {
    if (!ready) return;
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/banking/fints/accounts/${link.id}/assign`, {
      method: "POST",
      body: JSON.stringify({ property_id: propertyId, legal_entity_id: legalEntityId, kind, holder: holder.trim() }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.status === 403 ? t("createNoPermission") : res.message);
      return;
    }
    await onDone();
  }

  return (
    <div className="mt-2 flex flex-col gap-2 rounded border p-2" data-testid={`fints-create-${link.id}`}>
      <p className="text-xs text-muted">{t("createIntro", { suffix: link.iban_suffix })}</p>
      <label className={ui.label}>
        {t("createProperty")}
        <select className={ui.input} value={propertyId} onChange={(e) => setPropertyId(e.target.value)}>
          <option value="">{t("createPropertyChoose")}</option>
          {properties.map((p) => (
            <option key={p.id} value={p.id}>{p.number} {p.name}</option>
          ))}
        </select>
      </label>
      <label className={ui.label}>
        {t("createKind")}
        <select className={ui.input} value={kind} onChange={(e) => setKind(e.target.value as InlineKind)}>
          {INLINE_KINDS.map((k) => (
            <option key={k} value={k}>{tk(k)}</option>
          ))}
        </select>
      </label>
      <label className={ui.label}>
        {t("createEntity")}
        <select className={ui.input} value={legalEntityId} onChange={(e) => setLegalEntityId(e.target.value)} disabled={owners.length === 0}>
          {owners.map((o) => (
            <option key={o.id} value={o.id}>{o.name} ({te(o.kind)})</option>
          ))}
        </select>
      </label>
      {propertyId && owners.length === 0 ? <p className={ui.help}>{t("createNoOwner")}</p> : null}
      <label className={ui.label}>
        {t("createHolder")}
        <input className={ui.input} value={holder} onChange={(e) => setHolder(e.target.value)} maxLength={200} />
      </label>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      <div className={ui.formActions}>
        <button type="button" className={ui.primary} disabled={!ready || busy} onClick={submit}>
          {busy ? t("createBusy") : t("createSubmit")}
        </button>
      </div>
    </div>
  );
}

/** FinTS-Adresse der Bank je Verbindung (Bankfusion, neues Rechenzentrum): zeigt die
 *  verwendete Adresse und ihre Herkunft, erlaubt eine manuelle Adresse (mit erneuter PIN-Eingabe,
 *  es wird kein Anmeldeversuch gestartet) und die Rückkehr zur Adresse der Institutsliste. */
function FinTsAddress({
  connection,
  highlight,
  onChanged,
}: {
  connection: FinTsConnection;
  highlight: boolean;
  onChanged: () => Promise<void> | void;
}) {
  const t = useTranslations("FinTs");
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [pin, setPin] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const current = connection.fints_url;
  if (!current) return null;
  const manual = connection.fints_url_manual ?? null;

  async function save(next: string | null) {
    setBusy(true);
    setError(null);
    setMessage(null);
    const result = await bff<FinTsConnection>(`/api/bff/banking/fints/connections/${connection.id}`, {
      method: "PATCH",
      body: JSON.stringify(next === null ? { fints_url: null } : { fints_url: next, pin }),
    });
    setBusy(false);
    setPin("");
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setUrl("");
    setOpen(false);
    setMessage(next === null ? t("urlResetDone") : t("urlSaved"));
    await onChanged();
  }

  return (
    <div className="mt-2 text-xs" data-testid="fints-address">
      <span className="font-medium">{t("urlTitle")}</span>
      <span className="ml-1">
        <span className={ui.mono} title={current}>{hostOf(current)}</span>
        <span className="ml-1 text-muted">({manual ? t("urlSourceManual") : t("urlSourceList")})</span>
      </span>
      {!open ? (
        <button
          type="button"
          className={`${ui.buttonSm} ml-2`}
          disabled={busy || !!connection.open_session_id}
          onClick={() => {
            setOpen(true);
            setMessage(null);
          }}
        >
          {highlight ? t("urlCheck") : t("urlChange")}
        </button>
      ) : null}
      {message ? <p className={`${ui.notice} mt-1`}>{message}</p> : null}
      {error ? <p role="alert" className={`${ui.alert} mt-1`}>{error}</p> : null}
      {open ? (
        <form
          aria-label={t("urlTitle")}
          className="mt-2 flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            save(url.trim());
          }}
        >
          <p className={ui.help}>{t("urlHelp")}</p>
          <label className="flex flex-col gap-1 text-sm">
            {t("urlInput")}
            <input
              className={ui.input}
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder={t("urlPlaceholder")}
              autoComplete="off"
              aria-label={t("urlInput")}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            {t("urlPin")}
            <input
              className={ui.input}
              type="password"
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              autoComplete="current-password"
              aria-label={t("urlPin")}
            />
          </label>
          <div className={ui.formActions}>
            <button type="submit" className={ui.primary} disabled={busy || !url.trim() || !pin}>
              {t("urlSave")}
            </button>
            {manual ? (
              <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => save(null)}>
                {t("urlReset")}
              </button>
            ) : null}
            <button
              type="button"
              className={ui.buttonSm}
              disabled={busy}
              onClick={() => {
                setOpen(false);
                setError(null);
                setPin("");
              }}
            >
              {t("urlCancel")}
            </button>
          </div>
        </form>
      ) : null}
    </div>
  );
}

/** "Bankverbindungen (FinTS)" auf /bank: Liste mit Stand, Aktualisieren, erneute Freigabe,
 *  Trennen und der Dialog "Bank verbinden". Nur lesend: keine Zahlungen (G2 geschlossen). */
export function FinTsConnections() {
  const t = useTranslations("FinTs");
  const [connections, setConnections] = useState<FinTsConnection[] | null>(null);
  const [showDisconnected, setShowDisconnected] = useShowDisconnected();
  // null: unknown or endpoint unavailable (button stays); false: MHVP_FINTS_PRODUCT_ID missing.
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [dialog, setDialog] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [activeSession, setActiveSession] = useState<{ connectionId: string; sessionId: string } | null>(null);
  const [pinFor, setPinFor] = useState<{ connectionId: string; pin: string } | null>(null);

  const load = useCallback(async () => {
    const list = await bff<FinTsConnection[]>("/api/bff/banking/fints/connections");
    if (list.ok) {
      setConnections(list.data);
      setError(null);
    } else if (list.status === 401 || list.status === 403) {
      setConnections([]);
    } else {
      setConnections([]);
      setError(list.message);
    }
  }, []);

  useEffect(() => {
    load();
    bff<{ configured: boolean }>("/api/bff/banking/fints/config").then((result) => {
      if (result.ok && typeof result.data?.configured === "boolean") setConfigured(result.data.configured);
    });
  }, [load]);

  async function act<T>(path: string, init?: RequestInit, okMessage?: string): Promise<T | null> {
    setBusy(true);
    setError(null);
    setMessage(null);
    const result = await bff<T>(path, init);
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return null;
    }
    if (okMessage) setMessage(okMessage);
    await load();
    return result.data;
  }

  async function refresh(c: FinTsConnection) {
    const session = await act<FinTsSession>(`/api/bff/banking/fints/connections/${c.id}/refresh`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    if (session) setActiveSession({ connectionId: c.id, sessionId: session.id });
  }

  async function restart(c: FinTsConnection) {
    const body = pinFor?.connectionId === c.id && pinFor.pin ? { pin: pinFor.pin } : {};
    const session = await act<FinTsSession>(`/api/bff/banking/fints/connections/${c.id}/restart`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    setPinFor(null);
    if (session) setActiveSession({ connectionId: c.id, sessionId: session.id });
  }

  async function disconnect(c: FinTsConnection) {
    if (!window.confirm(t("disconnectConfirm", { bank: c.bank_name }))) return;
    await act(`/api/bff/banking/fints/connections/${c.id}`, { method: "DELETE" }, t("disconnected"));
  }

  const hiddenCount = (connections ?? []).filter((c) => isDisconnected(c.status)).length;
  const visible = connections === null ? null : showDisconnected ? connections : connections.filter((c) => !isDisconnected(c.status));

  return (
    <section className={ui.card}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className={ui.h2}>{t("title")}</h2>
        {configured !== false ? (
          <button type="button" className={ui.primary} onClick={() => setDialog(true)}>
            {t("connect")}
          </button>
        ) : null}
      </div>
      <p className="mt-1 text-sm text-muted">{t("intro")}</p>
      {configured === false ? (
        <p role="status" data-testid="fints-not-configured" className={`${ui.notice} mt-2`}>
          {t("notConfigured")}
        </p>
      ) : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      {message ? <p className={ui.notice}>{message}</p> : null}
      <DisconnectedToggle count={hiddenCount} show={showDisconnected} onChange={setShowDisconnected} />
      {visible === null ? (
        <p className="mt-3 text-sm text-muted">{t("loading")}</p>
      ) : visible.length === 0 ? (
        <p className="mt-3 text-sm text-muted">{t("noConnections")}</p>
      ) : (
        <div className="mt-3 flex flex-col gap-3">
          {visible.map((c) => (
            <div key={c.id} className="rounded-lg border border-border p-3" data-testid="fints-connection">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium">
                  {c.bank_name}
                  <span className="ml-1 text-xs text-muted">BLZ {c.blz}</span>
                </span>
                <StatusPill variant={STATUS_VARIANT[c.status] ?? "neutral"} label={t(`status.${c.status}`)} />
              </div>
              <p className="mt-1 text-xs text-muted">
                {c.last_sync_at ? t("lastSync", { when: formatDateTime(c.last_sync_at) }) : t("neverSynced")}
                {c.sca_due_on ? <span className="ml-2">{t("scaValidUntil", { date: formatDate(c.sca_due_on) })}</span> : null}
              </p>
              {c.pin_blocked ? (
                <div className={`${ui.warning} mt-2 flex flex-col gap-2`}>
                  <span>{c.last_error_code === "MHVP-BANK-0010" ? t("lockedBlocked") : t("pinBlocked")}</span>
                  {c.last_error_code && CHECK_STEP_CODES.includes(c.last_error_code) && c.last_error ? (
                    <span className="whitespace-pre-line text-xs">{c.last_error}</span>
                  ) : null}
                  <label className="flex flex-col gap-1 text-sm">
                    {t("pinAgain")}
                    <input
                      className={ui.input}
                      type="password"
                      value={pinFor?.connectionId === c.id ? pinFor.pin : ""}
                      onChange={(e) => setPinFor({ connectionId: c.id, pin: e.target.value })}
                      aria-label={t("pinAgain")}
                    />
                  </label>
                  <button type="button" className={ui.buttonSm} disabled={busy || !(pinFor?.connectionId === c.id && pinFor.pin)} onClick={() => restart(c)}>
                    {t("reauthorize")}
                  </button>
                </div>
              ) : c.sca_due || c.status === "update_required" ? (
                <p className={`${ui.warning} mt-2`}>{t("scaDue")}</p>
              ) : null}
              {c.last_error && !c.pin_blocked ? (
                <p className="mt-1 whitespace-pre-line text-xs text-danger-fg" data-testid="fints-last-error">
                  {c.last_error}
                </p>
              ) : null}
              {c.last_error_code && CHECK_STEP_CODES.includes(c.last_error_code) ? (
                <p className="mt-1 text-xs text-muted">{t("handbookHint")}</p>
              ) : null}
              {c.status !== "disabled" ? (
                <FinTsAddress connection={c} highlight={c.last_error_code === "MHVP-BANK-0013"} onChanged={load} />
              ) : null}
              {c.status !== "disabled" ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  <button type="button" className={ui.buttonSm} disabled={busy || c.pin_blocked || !!c.open_session_id} onClick={() => refresh(c)}>
                    {t("refresh")}
                  </button>
                  {!c.pin_blocked ? (
                    <button type="button" className={ui.buttonSm} disabled={busy || !!c.open_session_id} onClick={() => restart(c)}>
                      {t("reauthorize")}
                    </button>
                  ) : null}
                  {c.open_session_id && activeSession?.sessionId !== c.open_session_id ? (
                    <button type="button" className={ui.buttonSm} onClick={() => setActiveSession({ connectionId: c.id, sessionId: c.open_session_id! })}>
                      {t("openSession")}
                    </button>
                  ) : null}
                  <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => disconnect(c)}>
                    {t("disconnect")}
                  </button>
                </div>
              ) : null}
              {activeSession?.connectionId === c.id ? (
                <div className="mt-2 rounded border border-border p-2">
                  <FinTsSessionPanel
                    key={activeSession.sessionId}
                    sessionId={activeSession.sessionId}
                    onDone={async () => {
                      setMessage(t("refreshed"));
                      await load();
                    }}
                    onFailed={async () => {
                      await load();
                    }}
                  />
                  <button type="button" className={`${ui.buttonSm} mt-2`} onClick={() => setActiveSession(null)}>
                    {t("close")}
                  </button>
                </div>
              ) : null}
              <div className="mt-2">
                <FinTsAccountTable connection={c} onChanged={load} />
              </div>
            </div>
          ))}
        </div>
      )}
      {dialog ? <FinTsConnectDialog onClose={() => setDialog(false)} onChanged={load} /> : null}
    </section>
  );
}
