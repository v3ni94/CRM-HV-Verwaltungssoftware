"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type DispatchRecord = {
  channel: "post" | "email" | "portal";
  sent_on?: string | null;
  evidence_kind?: string | null;
  evidence_ref?: string | null;
};

export type LetterRecordBody = {
  letter_date?: string;
  ticket_id?: string;
  dispatch?: DispatchRecord;
  contact_id?: string;
};

export type LetterRecordResult = {
  document_id: string;
  title: string;
  dispatch: { channel: string; status: string } | null;
};

type Hit = { id: string; display_name: string };
type TicketHit = { id: string; number: number; title: string | null };
const CHANNELS = ["none", "post", "email", "portal"] as const;
const EVIDENCE = ["none", "registered_mail", "courier", "hand_delivery", "email_log", "portal_read", "other"] as const;

/** Contact search for the recipient (name only, data minimisation), same pattern as the
 *  successor field of the termination form. */
function RecipientField({ value, onChange }: { value: Hit | null; onChange: (hit: Hit | null) => void }) {
  const t = useTranslations("LetterRecord");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const search = async (q: string) => {
    setQuery(q);
    if (q.trim().length < 2) {
      setHits([]);
      return;
    }
    const res = await bff<{ items: Hit[] }>(`/api/bff/contacts?q=${encodeURIComponent(q.trim())}&page_size=8`);
    setHits(res.ok ? res.data.items.map((c) => ({ id: c.id, display_name: c.display_name })) : []);
  };
  return (
    <div className="flex flex-col gap-1">
      <span className={ui.label}>{t("recipient")}</span>
      {value ? (
        <span className="flex items-center gap-2 text-sm">
          <span className={ui.badgeGold} data-testid="letter-recipient">
            {value.display_name}
          </span>
          <button type="button" className={ui.buttonSm} onClick={() => onChange(null)}>
            {t("recipientClear")}
          </button>
        </span>
      ) : (
        <>
          <input className={ui.input} value={query} onChange={(e) => void search(e.target.value)} placeholder={t("recipientSearch")} aria-label={t("recipient")} data-testid="letter-recipient-search" />
          {hits.length ? (
            <ul className="flex flex-col gap-1">
              {hits.map((h) => (
                <li key={h.id}>
                  <button type="button" className={ui.buttonSm} onClick={() => onChange(h)}>
                    {h.display_name}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </>
      )}
    </div>
  );
}

function TicketField({ value, onChange }: { value: TicketHit | null; onChange: (hit: TicketHit | null) => void }) {
  const t = useTranslations("LetterRecord");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<TicketHit[]>([]);
  const search = async (q: string) => {
    setQuery(q);
    if (q.trim().length < 2) {
      setHits([]);
      return;
    }
    const params = new URLSearchParams({ q: q.trim(), limit: "8" });
    const res = await bff<TicketHit[]>(`/api/bff/tickets?${params.toString()}`);
    setHits(res.ok ? res.data : []);
  };
  return (
    <div className="flex flex-col gap-1">
      <span className={ui.label}>{t("ticket")}</span>
      {value ? (
        <span className="flex items-center gap-2 text-sm">
          <span className={ui.badgeInfo} data-testid="letter-ticket">
            #{value.number} {value.title ?? ""}
          </span>
          <button type="button" className={ui.buttonSm} onClick={() => onChange(null)}>
            {t("ticketNone")}
          </button>
        </span>
      ) : (
        <>
          <input className={ui.input} value={query} onChange={(e) => void search(e.target.value)} placeholder={t("recipientSearch")} aria-label={t("ticket")} data-testid="letter-ticket-search" />
          {hits.length ? (
            <ul className="flex flex-col gap-1">
              {hits.map((h) => (
                <li key={h.id}>
                  <button type="button" className={ui.buttonSm} onClick={() => onChange(h)}>
                    #{h.number} {h.title ?? ""}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </>
      )}
    </div>
  );
}

type Props = {
  /** POST target under /api/bff. */
  path: string;
  /** Recipient: `search` shows a contact search (required), `fixed` names the recipient. */
  recipient: { kind: "search" } | { kind: "fixed"; label: string };
  /** Portal channel refused (rent increase: G3). */
  portalLocked?: boolean;
  canCreate: boolean;
  requiredPermission: string;
  extraBody?: Record<string, unknown>;
  onCreated?: (result: LetterRecordResult) => void;
};

/** Letter on the letterhead with dispatch record (M12 gaps): one form for the
 *  Nachforderungsschreiben and the rent increase letter. The PDF is filed as a document;
 *  the dispatch record documents channel, date, user and reference. Nothing is sent. */
export function LetterRecordForm({ path, recipient, portalLocked = false, canCreate, requiredPermission, extraBody, onCreated }: Props) {
  const t = useTranslations("LetterRecord");
  const [contact, setContact] = useState<Hit | null>(null);
  const [ticket, setTicket] = useState<TicketHit | null>(null);
  const [letterDate, setLetterDate] = useState("");
  const [channel, setChannel] = useState<(typeof CHANNELS)[number]>("none");
  const [sentOn, setSentOn] = useState("");
  const [evidenceKind, setEvidenceKind] = useState<(typeof EVIDENCE)[number]>("none");
  const [evidenceRef, setEvidenceRef] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<LetterRecordResult | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (recipient.kind === "search" && !contact) {
      setError(t("recipientRequired"));
      return;
    }
    const body: LetterRecordBody & Record<string, unknown> = { ...(extraBody ?? {}) };
    if (contact) body.contact_id = contact.id;
    if (letterDate) body.letter_date = letterDate;
    if (ticket) body.ticket_id = ticket.id;
    if (channel !== "none") {
      body.dispatch = {
        channel,
        sent_on: sentOn || null,
        evidence_kind: evidenceKind === "none" ? null : evidenceKind,
        evidence_ref: evidenceRef.trim() || null,
      };
    }
    setBusy(true);
    const res = await bff<LetterRecordResult>(`/api/bff/${path}`, { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setResult(res.data);
    onCreated?.(res.data);
  }

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="letter-record-title" data-testid="letter-record">
      <h2 id="letter-record-title" className={ui.h2}>
        {t("title")}
      </h2>
      <p className={ui.help}>{t("intro")}</p>
      {!canCreate ? <p className="text-xs text-muted">{t("readOnly", { permission: requiredPermission })}</p> : null}
      {canCreate ? (
        <form onSubmit={submit} className="flex flex-col gap-3">
          {recipient.kind === "search" ? (
            <RecipientField value={contact} onChange={setContact} />
          ) : (
            <p className="text-sm">
              <span className={ui.label}>{t("recipient")}</span> {recipient.label}
            </p>
          )}
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("letterDate")}</span>
              <input type="date" className={ui.input} value={letterDate} onChange={(e) => setLetterDate(e.target.value)} data-testid="letter-date" />
            </label>
            <TicketField value={ticket} onChange={setTicket} />
          </div>
          <fieldset className="flex flex-col gap-2 rounded-md border border-border p-3">
            <legend className={ui.label}>{t("record")}</legend>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("channel")}</span>
              <select className={ui.input} value={channel} onChange={(e) => setChannel(e.target.value as (typeof CHANNELS)[number])} data-testid="letter-channel">
                {CHANNELS.filter((c) => !(portalLocked && c === "portal")).map((c) => (
                  <option key={c} value={c}>
                    {t(`channels.${c}`)}
                  </option>
                ))}
              </select>
            </label>
            {portalLocked ? <p className="text-xs text-muted">{t("portalGate")}</p> : null}
            {channel !== "none" ? (
              <div className="grid gap-3 sm:grid-cols-3">
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("sentOn")}</span>
                  <input type="date" className={ui.input} value={sentOn} onChange={(e) => setSentOn(e.target.value)} data-testid="letter-sent-on" />
                </label>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("evidenceKind")}</span>
                  <select className={ui.input} value={evidenceKind} onChange={(e) => setEvidenceKind(e.target.value as (typeof EVIDENCE)[number])}>
                    {EVIDENCE.map((e) => (
                      <option key={e} value={e}>
                        {t(`evidence.${e}`)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("evidenceRef")}</span>
                  <input className={ui.input} value={evidenceRef} onChange={(e) => setEvidenceRef(e.target.value)} maxLength={200} data-testid="letter-evidence-ref" />
                </label>
              </div>
            ) : null}
          </fieldset>
          <div className={ui.formActions}>
            <button type="submit" className={ui.primary} disabled={busy} data-testid="letter-create">
              {busy ? t("creating") : t("create")}
            </button>
          </div>
        </form>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {result ? (
        <p className={ui.success} data-testid="letter-result">
          {t("created", { title: result.title })}{" "}
          <Link href={`/dokumente/${result.document_id}`} className="underline">
            {t("openDocument")}
          </Link>
          {result.dispatch ? <span className="block text-xs">{t("dispatchRecorded", { channel: t(`channels.${result.dispatch.channel}`), status: result.dispatch.status })}</span> : null}
        </p>
      ) : null}
    </section>
  );
}
