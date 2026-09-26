"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import type { BoardEngagementDetail as Detail } from "@/components/portal/types";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

function amount(value: string | null): string {
  if (value === null) return "";
  return `${new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value))} EUR`;
}

/** Prüfungsraum eines Prüfauftrags (7.9.2 PÜ07, PÜ08, A52): Positionen mit Prüfstatus, Belege
 *  (nur die freigegebenen Belege des Prüfauftrags), Vermerke und Rückfragen des Beirats mit den
 *  Antworten der Verwaltung. Der Beirat bucht nichts, gibt nichts frei und ändert keine
 *  Abrechnung; die einzige Aktion ist der Vermerk oder die Rückfrage. */
export function BoardEngagementDetail({ detail }: { detail: Detail }) {
  const t = useTranslations("Audit");
  const format = useFormatter();
  const router = useRouter();
  const [kind, setKind] = useState<"note" | "question">("question");
  const [text, setText] = useState("");
  const [itemId, setItemId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const date = (value: string | null) =>
    value ? format.dateTime(new Date(value), { day: "2-digit", month: "2-digit", year: "numeric" }) : "";
  const positionLabel = (id: string | null) => {
    if (!id) return t("wholeEngagement");
    const index = detail.positions.findIndex((p) => p.id === id);
    return index >= 0 ? t("positionNumber", { n: index + 1 }) : t("wholeEngagement");
  };

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (text.trim().length === 0) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    const result = await bff(`/api/bff/portal/board/engagements/${detail.id}/notes`, {
      method: "POST",
      body: JSON.stringify({ kind, text: text.trim(), audit_item_id: itemId || null }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setText("");
    setNotice(kind === "question" ? t("questionSent") : t("noteSaved"));
    router.refresh();
  }

  return (
    <div className={ui.pageGap}>
      <div className={`${ui.card} flex flex-col gap-1`}>
        <h1 className={ui.title}>{detail.legal_entity_name ?? detail.legal_entity_id}</h1>
        <p className="text-sm text-muted">{detail.purpose}</p>
        <p className="text-xs text-subtle">
          {t("period")} {date(detail.period_from)} bis {date(detail.period_to)} · {t(`sampling.${detail.sampling}`)}
        </p>
        <p className="text-sm">
          {t("overallStatus")}: <span className={ui.badge}>{detail.overall_status}</span>
        </p>
      </div>
      <p className={ui.notice}>{t("roleNotice")}</p>

      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{t("positions")}</h2>
        {detail.positions.length === 0 ? <p className={ui.help}>{t("noPositions")}</p> : null}
        <ul className="flex flex-col gap-2">
          {detail.positions.map((p, index) => (
            <li key={p.id} className={`${ui.card} flex flex-col gap-1`}>
              <span className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium">
                  {t("positionNumber", { n: index + 1 })}
                  {p.booking_text ? `: ${p.booking_text}` : ""}
                </span>
                <span className={ui.badge}>{t(`status.${p.status}`)}</span>
              </span>
              <span className="text-sm text-muted">
                {p.booking_date ? `${date(p.booking_date)} · ` : ""}
                {amount(p.amount)}
                {p.booking_reference ? ` · ${p.booking_reference}` : ""}
              </span>
              {p.outdated_reason ? <span className={ui.alert}>{p.outdated_reason}</span> : null}
              {p.note ? <span className="text-sm">{t("managementNote")}: {p.note}</span> : null}
              {p.question ? <span className="text-sm">{t("managementQuestion")}: {p.question}</span> : null}
              {p.answer ? <span className="text-sm">{t("managementAnswer")}: {p.answer}</span> : null}
            </li>
          ))}
        </ul>
      </section>

      {detail.cost_items.length > 0 ? (
        <section className="flex flex-col gap-2">
          <h2 className={ui.h2}>{t("costItems")}</h2>
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("costLabel")}</th>
                <th>{t("costBasis")}</th>
                <th className="text-right">{t("costAmount")}</th>
              </tr>
            </thead>
            <tbody>
              {detail.cost_items.map((c) => (
                <tr key={c.id}>
                  <td>{c.label}</td>
                  <td>{c.basis}</td>
                  <td className="text-right">{amount(c.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{t("documents")}</h2>
        {detail.documents.length === 0 ? <p className={ui.help}>{t("noDocuments")}</p> : null}
        <ul className="flex flex-col gap-2">
          {detail.documents.map((d) => (
            <li key={d.id} className={`${ui.card} flex flex-wrap items-center justify-between gap-2`}>
              <span className="flex flex-col gap-0.5">
                <span className="font-medium">{d.title}</span>
                <span className="text-xs text-subtle">{positionLabel(d.audit_item_id)}</span>
              </span>
              <a
                href={`/api/portal-files/portal/board/engagements/${detail.id}/documents/${d.id}`}
                className={ui.buttonSm}
                target="_blank"
                rel="noreferrer"
              >
                {t("open")}
              </a>
            </li>
          ))}
        </ul>
        <p className={ui.help}>{detail.read_receipt_note}</p>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{t("notes")}</h2>
        {detail.notes.length === 0 ? <p className={ui.help}>{t("noNotes")}</p> : null}
        <ul className="flex flex-col gap-2">
          {detail.notes.map((n) => (
            <li key={n.id} className={`${ui.card} flex flex-col gap-1`}>
              <span className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs text-subtle">
                  {date(n.created_at)} · {positionLabel(n.audit_item_id)}
                </span>
                <span className={ui.badge}>{t(`kind.${n.kind}`)}</span>
              </span>
              <span className="text-sm">{n.text}</span>
              {n.answer ? (
                <span className="text-sm text-muted">
                  {t("managementAnswer")} ({date(n.answered_at)}): {n.answer}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      </section>

      <form onSubmit={submit} className={`${ui.card} flex flex-col gap-3`}>
        <h2 className={ui.h2}>{t("newNote")}</h2>
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
        {notice ? <p className={ui.success}>{notice}</p> : null}
        <div>
          <label htmlFor="note-kind" className={ui.label}>
            {t("kindLabel")}
          </label>
          <select id="note-kind" className={ui.input} value={kind} onChange={(e) => setKind(e.target.value as "note" | "question")}>
            <option value="question">{t("kind.question")}</option>
            <option value="note">{t("kind.note")}</option>
          </select>
        </div>
        <div>
          <label htmlFor="note-position" className={ui.label}>
            {t("positionLabel")}
          </label>
          <select id="note-position" className={ui.input} value={itemId} onChange={(e) => setItemId(e.target.value)}>
            <option value="">{t("wholeEngagement")}</option>
            {detail.positions.map((p, index) => (
              <option key={p.id} value={p.id}>
                {t("positionNumber", { n: index + 1 })}
                {p.booking_text ? `: ${p.booking_text}` : ""}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="note-text" className={ui.label}>
            {t("textLabel")}
          </label>
          <textarea id="note-text" rows={4} className={ui.input} value={text} onChange={(e) => setText(e.target.value)} />
        </div>
        <button type="submit" className={`${ui.button} ${ui.actionFull}`} disabled={busy || text.trim().length === 0}>
          {t("submit")}
        </button>
      </form>
    </div>
  );
}
