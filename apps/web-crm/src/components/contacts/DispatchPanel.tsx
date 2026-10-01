"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Zustellung am Kontakt (M23, 11.3): ein abgelegtes Dokument je Zustellweg vorbereiten und
 *  Versand oder Zugang mit Nachweis erfassen. Die Plattform versendet nichts selbst: E-Mail
 *  wird ein Entwurf, Post eine vorbereitete Zustellung (auf Wunsch mit Postauftrag). */
export const CHANNELS = ["post", "email", "portal", "sms", "registered", "courier"] as const;
export const EVIDENCE_KINDS = [
  "registered_mail",
  "courier",
  "hand_delivery",
  "email_log",
  "portal_read",
  "sms_log",
  "other",
] as const;

export type DispatchRow = {
  id: string;
  channel: string;
  status: string;
  document_id: string;
};

export function DispatchPanel({
  contactId,
  documents,
  canCreate,
  canRecord,
}: {
  contactId: string;
  documents: { id: string; title: string }[];
  canCreate: boolean;
  canRecord: boolean;
}) {
  const t = useTranslations("Dispatch");
  const [documentId, setDocumentId] = useState(documents[0]?.id ?? "");
  const [channel, setChannel] = useState<(typeof CHANNELS)[number]>("post");
  const [postal, setPostal] = useState(true);
  const [rows, setRows] = useState<DispatchRow[]>([]);
  const [evidence, setEvidence] = useState<Record<string, { kind: string; ref: string }>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    setBusy(true);
    setError(null);
    const res = await bff<DispatchRow & { further_dispatches: DispatchRow[] }>(
      "/api/bff/dispatches",
      {
        method: "POST",
        body: JSON.stringify({
          document_id: documentId,
          contact_id: contactId,
          channel,
          ...(channel === "post" && !postal ? { submit_postal: false } : {}),
        }),
      },
    );
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    const { further_dispatches: further, ...first } = res.data;
    setRows((r) => [first, ...further, ...r]);
  }

  async function record(row: DispatchRow) {
    const entry = evidence[row.id] ?? { kind: "", ref: "" };
    setBusy(true);
    setError(null);
    const res = await bff<DispatchRow>(`/api/bff/dispatches/${row.id}/evidence`, {
      method: "POST",
      body: JSON.stringify({
        status: "delivered",
        evidence_kind: entry.kind,
        evidence_ref: entry.ref,
      }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setRows((all) => all.map((x) => (x.id === row.id ? { ...x, status: res.data.status } : x)));
  }

  if (!canCreate) return <p className="text-sm text-muted">{t("noRight")}</p>;
  return (
    <div className="flex flex-col gap-3">
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {documents.length === 0 ? (
        <p className="text-sm text-muted">{t("noDocuments")}</p>
      ) : (
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("document")}</span>
            <select
              className={ui.input}
              value={documentId}
              onChange={(e) => setDocumentId(e.target.value)}
            >
              {documents.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.title}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("channel")}</span>
            <select
              className={ui.input}
              value={channel}
              onChange={(e) => setChannel(e.target.value as (typeof CHANNELS)[number])}
            >
              {CHANNELS.map((c) => (
                <option key={c} value={c}>
                  {t(`channels.${c}`)}
                </option>
              ))}
            </select>
          </label>
          {channel === "post" ? (
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={postal}
                onChange={(e) => setPostal(e.target.checked)}
              />
              {t("submitPostal")}
            </label>
          ) : null}
          <button
            type="button"
            className={ui.buttonSm}
            disabled={busy || !documentId}
            onClick={() => void create()}
          >
            {t("prepare")}
          </button>
        </div>
      )}
      <p className="text-xs text-muted">{t("hint")}</p>
      {rows.length > 0 ? (
        <ul className="flex flex-col gap-2">
          {rows.map((row) => (
            <li key={row.id} className={ui.card}>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className={ui.badge}>{t(`channels.${row.channel as (typeof CHANNELS)[number]}`)}</span>
                <span className="text-xs text-muted">{t(`status.${row.status as "prepared"}`)}</span>
              </div>
              {canRecord && row.status !== "delivered" ? (
                <div className="mt-2 flex flex-wrap items-end gap-2">
                  <label className="flex flex-col gap-1">
                    <span className={ui.label}>{t("evidenceKind")}</span>
                    <select
                      className={ui.input}
                      value={evidence[row.id]?.kind ?? ""}
                      onChange={(e) =>
                        setEvidence((m) => ({
                          ...m,
                          [row.id]: { kind: e.target.value, ref: m[row.id]?.ref ?? "" },
                        }))
                      }
                    >
                      <option value="">{t("choose")}</option>
                      {EVIDENCE_KINDS.map((k) => (
                        <option key={k} value={k}>
                          {t(`evidence.${k}`)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className={ui.label}>{t("evidenceRef")}</span>
                    <input
                      className={ui.input}
                      value={evidence[row.id]?.ref ?? ""}
                      onChange={(e) =>
                        setEvidence((m) => ({
                          ...m,
                          [row.id]: { kind: m[row.id]?.kind ?? "", ref: e.target.value },
                        }))
                      }
                    />
                  </label>
                  <button
                    type="button"
                    className={ui.buttonSm}
                    disabled={busy || !(evidence[row.id]?.kind && evidence[row.id]?.ref)}
                    onClick={() => void record(row)}
                  >
                    {t("recordDelivered")}
                  </button>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
