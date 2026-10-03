"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { ContactPicker, type PickedContact } from "@/components/hoa/ContactPicker";
import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { today } from "@/lib/today";
import { ui } from "@/lib/ui";
import { useBusy } from "@/lib/use-busy";

const CHANNELS = ["email", "letter", "portal", "phone", "in_person", "other"] as const;
type Channel = (typeof CHANNELS)[number];
type NextStatus = "in_progress" | "answered" | "rejected" | "withdrawn";

export type PrivacyAccessRequest = {
  id: string;
  contact_id: string;
  contact_name: string | null;
  received_on: string;
  channel: string;
  status: "received" | "in_progress" | "answered" | "rejected" | "withdrawn";
  note: string | null;
  closed_on: string | null;
  due_on: string | null;
  warn_on: string | null;
  state: "unconfigured" | "ok" | "warn" | "overdue" | "closed";
};

const NEXT: Record<string, NextStatus[]> = {
  received: ["in_progress", "answered", "rejected", "withdrawn"],
  in_progress: ["answered", "rejected", "withdrawn"],
};

/**
 * Auskunftsanträge (AK06, GAI-507): Eingang mit Datum und Weg erfassen, Status führen, Frist
 * aus der Mandanteneinstellung ohne Standardwert (AJ13-01). Die Fälligkeit ist eine
 * Orientierung und zu prüfen; die Auskunft selbst entsteht über den geprüften Auskunftsexport.
 */
export function PrivacyAccessRequests({ canManage }: { canManage: boolean }) {
  const t = useTranslations("PrivacyAccessRequests");
  const [rows, setRows] = useState<PrivacyAccessRequest[] | null>(null);
  const [contact, setContact] = useState<PickedContact | null>(null);
  const [received, setReceived] = useState(today());
  const [channel, setChannel] = useState<Channel>("email");
  const [note, setNote] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { busy, guard } = useBusy();

  const load = useCallback(async () => {
    const res = await bff<PrivacyAccessRequest[]>("/api/bff/privacy/access-requests");
    if (res.ok) setRows(res.data);
    else setError(res.message);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const create = guard(async () => {
    if (!contact) return;
    setMessage(null);
    setError(null);
    const res = await bff<PrivacyAccessRequest>("/api/bff/privacy/access-requests", {
      method: "POST",
      body: JSON.stringify({ contact_id: contact.id, received_on: received, channel, note: note.trim() || null }),
    });
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setContact(null);
    setNote("");
    setMessage(t("created"));
    await load();
  });

  const setStatus = guard(async (id: string, status: NextStatus) => {
    setMessage(null);
    setError(null);
    const res = await bff<PrivacyAccessRequest>(`/api/bff/privacy/access-requests/${id}/status`, {
      method: "POST",
      body: JSON.stringify({ status }),
    });
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setMessage(t("updated"));
    await load();
  });

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="privacy-access-title">
      <h2 id="privacy-access-title" className="text-base font-semibold">
        {t("title")}
      </h2>
      <p className="text-xs">{t("hint")}</p>
      {canManage ? (
        <div className="flex flex-col gap-2">
          <ContactPicker label={t("contact")} onPick={setContact} />
          {contact ? <p className="text-sm">{t("picked", { name: contact.display_name })}</p> : null}
          <div className="flex flex-wrap gap-3">
            <div className="w-44">
              <label className={ui.label} htmlFor="privacy-access-received">
                {t("received")}
              </label>
              <input
                id="privacy-access-received"
                type="date"
                className={ui.input}
                value={received}
                max={today()}
                onChange={(e) => setReceived(e.target.value)}
              />
            </div>
            <div className="w-44">
              <label className={ui.label} htmlFor="privacy-access-channel">
                {t("channel")}
              </label>
              <select
                id="privacy-access-channel"
                className={ui.input}
                value={channel}
                onChange={(e) => setChannel(e.target.value as Channel)}
              >
                {CHANNELS.map((c) => (
                  <option key={c} value={c}>
                    {t(`channels.${c}`)}
                  </option>
                ))}
              </select>
            </div>
            <div className="min-w-64 flex-1">
              <label className={ui.label} htmlFor="privacy-access-note">
                {t("note")}
              </label>
              <input
                id="privacy-access-note"
                className={ui.input}
                maxLength={1000}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </div>
          </div>
          <div>
            <button type="button" className={ui.primary} disabled={busy || !contact || !received} onClick={() => void create()}>
              {t("create")}
            </button>
          </div>
        </div>
      ) : null}
      {rows === null ? (
        <p className="text-sm">{t("loading")}</p>
      ) : rows.length === 0 ? (
        <p className="text-sm">{t("empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left">
                <th scope="col">{t("colContact")}</th>
                <th scope="col">{t("colReceived")}</th>
                <th scope="col">{t("colChannel")}</th>
                <th scope="col">{t("colStatus")}</th>
                <th scope="col">{t("colDue")}</th>
                <th scope="col">{t("colActions")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{r.contact_name ?? r.contact_id}</td>
                  <td>{formatDate(r.received_on)}</td>
                  <td>{t(`channels.${r.channel}`)}</td>
                  <td>{t(`statuses.${r.status}`)}</td>
                  <td>
                    {r.due_on ? formatDate(r.due_on) : null}{" "}
                    <span className={r.state === "overdue" ? "font-semibold text-red-700" : ""}>{t(`states.${r.state}`)}</span>
                  </td>
                  <td>
                    {canManage ? (
                      <span className="flex flex-wrap gap-1">
                        {(NEXT[r.status] ?? []).map((s) => (
                          <button key={s} type="button" className={ui.buttonSm} disabled={busy} onClick={() => void setStatus(r.id, s)}>
                            {t(`actions.${s}`)}
                          </button>
                        ))}
                      </span>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {message ? <p role="status" className={ui.success}>{message}</p> : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </section>
  );
}
