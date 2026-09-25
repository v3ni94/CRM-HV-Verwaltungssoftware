"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** One side of the merge preview (M36). Names are resolved, ids stay out of the UI. */
export type MergeSide = {
  id: string;
  number: number;
  title: string | null;
  status: string;
  priority: string;
  contact: string | null;
  property: string | null;
  messageCount: number;
};

type ListRow = {
  id: string;
  number: number;
  title: string | null;
  status: string;
  merged_into_ticket_id: string | null;
};

type Detail = {
  id: string;
  number: number;
  title: string | null;
  status: string;
  priority: string;
  contact_id: string | null;
  property_id: string | null;
  message_count?: number;
  comments?: unknown[];
};

async function loadSide(id: string): Promise<MergeSide | null> {
  const res = await bff<Detail>(`/api/bff/tickets/${id}`);
  if (!res.ok) return null;
  const d = res.data;
  const [contact, property] = await Promise.all([
    d.contact_id ? bff<{ display_name?: string | null }>(`/api/bff/contacts/${d.contact_id}/name`) : null,
    d.property_id ? bff<{ name?: string | null }>(`/api/bff/properties/${d.property_id}`) : null,
  ]);
  return {
    id: d.id,
    number: d.number,
    title: d.title,
    status: d.status,
    priority: d.priority,
    contact: contact?.ok ? (contact.data.display_name ?? null) : null,
    property: property?.ok ? (property.data.name ?? null) : null,
    messageCount: (d.message_count ?? 0) + (d.comments?.length ?? 0),
  };
}

function SideCard({ side, heading }: { side: MergeSide; heading: string }) {
  const t = useTranslations("Tickets");
  const rows: [string, string][] = [
    [t("number"), `#${side.number}`],
    [t("titleField"), side.title ?? ""],
    [t("status"), t(`statuses.${side.status}`)],
    [t("priority"), t(`priorities.${side.priority}`)],
    [t("merge.contact"), side.contact ?? t("merge.none")],
    [t("merge.property"), side.property ?? t("merge.none")],
    [t("merge.messages"), String(side.messageCount)],
  ];
  return (
    <div className={ui.card} data-testid="merge-side">
      <h3 className="mb-2 text-sm font-semibold">{heading}</h3>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted">{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function TicketMergeDialog({ source }: { source: MergeSide }) {
  const t = useTranslations("Tickets");
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ListRow[] | null>(null);
  const [target, setTarget] = useState<MergeSide | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setOpen(false);
    setQuery("");
    setResults(null);
    setTarget(null);
    setError(null);
  };

  const search = async () => {
    setBusy(true);
    setError(null);
    setTarget(null);
    const params = new URLSearchParams({ q: query.trim(), include_merged: "false", limit: "20" });
    const res = await bff<ListRow[]>(`/api/bff/tickets?${params.toString()}`);
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setResults(res.data.filter((r) => r.id !== source.id && !r.merged_into_ticket_id && r.status !== "closed"));
  };

  const pick = async (id: string) => {
    setBusy(true);
    setError(null);
    const side = await loadSide(id);
    setBusy(false);
    if (side) setTarget(side);
    else setError(t("merge.loadFailed"));
  };

  const confirm = async () => {
    if (!target) return;
    setBusy(true);
    setError(null);
    const res = await bff<{ id: string }>("/api/bff/tickets/merge", {
      method: "POST",
      body: JSON.stringify({ ticket_ids: [source.id], target_ticket_id: target.id }),
    });
    setBusy(false);
    if (res.ok) router.push(`/tickets/${res.data.id}`);
    else setError(res.message);
  };

  if (!open) {
    return (
      <div>
        <button type="button" className={ui.secondary} onClick={() => setOpen(true)}>
          {t("merge.action")}
        </button>
      </div>
    );
  }

  return (
    <section role="dialog" aria-modal="false" aria-labelledby="ticket-merge-title" className={`${ui.card} flex flex-col gap-3`}>
      <h2 id="ticket-merge-title" className={ui.h2}>
        {t("merge.title")}
      </h2>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void search();
        }}
      >
        <label className="flex flex-1 flex-col gap-1">
          <span className={ui.label}>{t("merge.searchLabel")}</span>
          <input className={ui.input} value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("merge.searchPlaceholder")} />
        </label>
        <button type="submit" className={ui.button} disabled={busy || !query.trim()}>
          {t("merge.search")}
        </button>
      </form>
      {results && results.length === 0 ? <p className="text-sm text-muted">{t("merge.noResults")}</p> : null}
      {results && results.length > 0 && !target ? (
        <ul className="flex flex-col gap-1" aria-label={t("merge.results")}>
          {results.map((r) => (
            <li key={r.id}>
              <button type="button" className={`${ui.buttonSm} w-full justify-start`} disabled={busy} onClick={() => void pick(r.id)}>
                #{r.number} {r.title ?? ""}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {target ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <SideCard side={source} heading={t("merge.sourceHeading")} />
            <SideCard side={target} heading={t("merge.targetHeading")} />
          </div>
          <p className={ui.notice}>{t("merge.hint")}</p>
        </>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div className={ui.formActions}>
        {target ? (
          <button type="button" className={ui.primary} disabled={busy} onClick={() => void confirm()}>
            {t("merge.confirm")}
          </button>
        ) : null}
        <button type="button" className={ui.button} disabled={busy} onClick={reset}>
          {t("merge.cancel")}
        </button>
      </div>
    </section>
  );
}
