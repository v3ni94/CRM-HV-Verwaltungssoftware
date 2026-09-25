"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";
import { EmptyState } from "@/components/ui/EmptyState";

type LearningKind = "webdav" | "carddav" | "caldav";
type LearningStatus = "pending" | "running" | "done" | "failed";

type LearningRunListItem = {
  id: string;
  kind: LearningKind;
  status: LearningStatus;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
};

type LearningRun = LearningRunListItem & {
  facts: Record<string, unknown> | null;
  diff: Record<string, unknown> | null;
};

type Page<T> = { data: T[]; meta: { page: number; per_page: number; total: number } };

const KINDS: LearningKind[] = ["webdav", "carddav", "caldav"];

function statusBadge(status: LearningStatus): string {
  if (status === "done") return ui.badgeSuccess;
  if (status === "failed") return ui.badgeDanger;
  if (status === "running") return ui.badgeWarning;
  return ui.badge;
}

/** Lernphase Immoware24 (M33): Auswahl der Art, Start eines Laufs, Liste der Laeufe und eine
 *  lesbare Detailansicht der Fakten und Aenderungen zum Vorlauf. Reine Leseerkundung des
 *  Immoware24-Spiegels, kein Schreibpfad. */
export function ImmowareLearning({ canStart }: { canStart: boolean }) {
  const t = useTranslations("Immoware.learning");
  const [kind, setKind] = useState<LearningKind>("webdav");
  const [runs, setRuns] = useState<LearningRunListItem[] | null>(null);
  const [starting, setStarting] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    void (async () => {
      const params = new URLSearchParams({ kind, page: "1", page_size: "50" });
      const res = await bff<Page<LearningRunListItem>>(`/api/bff/immoware/learning/runs?${params.toString()}`);
      if (!active) return;
      if (res.ok) setRuns(res.data.data);
    })();
    return () => {
      active = false;
    };
  }, [kind, reloadToken]);

  async function startRun() {
    setStarting(true);
    try {
      const res = await bff<LearningRun>("/api/bff/immoware/learning/runs", {
        method: "POST",
        body: JSON.stringify({ kind }),
      });
      if (res.ok) {
        setSelectedId(res.data.id);
        setReloadToken((n) => n + 1);
      }
    } finally {
      setStarting(false);
    }
  }

  if (selectedId) {
    return <LearningRunDetail runId={selectedId} onBack={() => setSelectedId(null)} />;
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2 border-b border-border-soft pb-2" role="tablist">
        {KINDS.map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={kind === value}
            className={kind === value ? ui.badgeGold : ui.badge}
            onClick={() => setKind(value)}
          >
            {t(`kinds.${value}`)}
          </button>
        ))}
      </div>
      {canStart ? (
        <div>
          <button type="button" className={ui.primary} onClick={() => void startRun()} disabled={starting}>
            {starting ? t("starting") : t("start")}
          </button>
        </div>
      ) : null}
      {runs === null ? (
        <p className="text-sm text-muted">…</p>
      ) : runs.length === 0 ? (
        <EmptyState title={t("empty")} />
      ) : (
        <div className={`${ui.card} overflow-x-auto p-0`}>
          <table className={ui.table} data-testid="immoware-learning-runs">
            <thead>
              <tr>
                <th>{t("list.columns.status")}</th>
                <th>{t("list.columns.started")}</th>
                <th>{t("list.columns.finished")}</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id}>
                  <td>
                    <button type="button" className="hover:underline" onClick={() => setSelectedId(run.id)}>
                      <span className={statusBadge(run.status)}>{t(`status.${run.status}`)}</span>
                    </button>
                  </td>
                  <td>{formatDateTime(run.started_at)}</td>
                  <td>{formatDateTime(run.finished_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function shareText(value: unknown): string {
  const n = typeof value === "number" ? value : 0;
  return `${(n * 100).toFixed(1)} %`;
}

function LearningRunDetail({ runId, onBack }: { runId: string; onBack: () => void }) {
  const t = useTranslations("Immoware.learning");
  const [run, setRun] = useState<LearningRun | null>(null);
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const load = async () => {
      const res = await bff<LearningRun>(`/api/bff/immoware/learning/runs/${runId}`);
      if (!active) return;
      if (res.ok) {
        setRun(res.data);
        if (res.data.status === "pending" || res.data.status === "running") {
          timer = setTimeout(load, 2000);
        }
      }
    };
    void load();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [runId]);

  if (!run) return <p className="text-sm text-muted">…</p>;

  const facts = run.facts ?? {};
  const diff = run.diff ?? {};
  const changes = Array.isArray(diff.changes) ? (diff.changes as string[]) : [];

  return (
    <div className="flex flex-col gap-4">
      <div>
        <button type="button" className={ui.buttonSm} onClick={onBack}>
          {t("back")}
        </button>
      </div>
      <div className="flex items-center gap-2">
        <h2 className={ui.h2}>{t("title", { kind: t(`kinds.${run.kind}`) })}</h2>
        <span className={statusBadge(run.status)}>{t(`status.${run.status}`)}</span>
      </div>
      {run.error ? <p className={ui.alert}>{t("detail.error", { error: run.error })}</p> : null}

      {run.status === "done" ? (
        <div className={ui.card}>
          <h3 className={ui.h2}>{t("detail.changes")}</h3>
          {diff.first_run ? (
            <p className="text-sm text-muted">{t("detail.firstRun")}</p>
          ) : changes.length > 0 ? (
            <ul className="list-inside list-disc text-sm text-fg">
              {changes.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">{t("detail.changedNo")}</p>
          )}
        </div>
      ) : null}

      {run.status === "done" && run.kind === "webdav" ? <WebdavFacts facts={facts} t={t} /> : null}
      {run.status === "done" && run.kind === "carddav" ? <CarddavFacts facts={facts} t={t} /> : null}
      {run.status === "done" && run.kind === "caldav" ? <CaldavFacts facts={facts} t={t} /> : null}

      <details className={ui.card}>
        <summary className="cursor-pointer select-none text-sm font-medium" onClick={() => setShowRaw(!showRaw)}>
          {t("detail.rawFacts")}
        </summary>
        <pre className="mt-2 max-h-96 overflow-auto text-xs">{JSON.stringify({ facts, diff }, null, 2)}</pre>
      </details>
    </div>
  );
}

function WebdavFacts({ facts, t }: { facts: Record<string, unknown>; t: ReturnType<typeof useTranslations> }) {
  const folders = Array.isArray(facts.folders) ? (facts.folders as Record<string, unknown>[]) : [];
  return (
    <div className={`${ui.card} overflow-x-auto`}>
      <div className="mb-3 flex flex-wrap gap-4 text-sm">
        <span>
          {t("detail.webdav.folderCount")}: <strong>{String(facts.folder_count ?? 0)}</strong>
        </span>
        <span>
          {t("detail.webdav.objectNumberShare")}: <strong>{shareText(facts.object_number_share)}</strong>
        </span>
      </div>
      <table className={ui.table}>
        <thead>
          <tr>
            <th>{t("detail.webdav.columns.path")}</th>
            <th>{t("detail.webdav.columns.depth")}</th>
            <th>{t("detail.webdav.columns.files")}</th>
            <th>{t("detail.webdav.columns.bytes")}</th>
            <th>{t("detail.webdav.columns.objectNumber")}</th>
          </tr>
        </thead>
        <tbody>
          {folders.map((f, i) => (
            <tr key={i}>
              <td>{String(f.path ?? "")}</td>
              <td>{String(f.depth ?? "")}</td>
              <td>{String(f.file_count ?? 0)}</td>
              <td>{String(f.total_bytes ?? 0)}</td>
              <td>{f.has_object_number ? "✓" : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CarddavFacts({ facts, t }: { facts: Record<string, unknown>; t: ReturnType<typeof useTranslations> }) {
  const usage = (facts.field_usage as Record<string, number>) ?? {};
  const duplicates = Array.isArray(facts.duplicate_candidates)
    ? (facts.duplicate_candidates as { email: string; contact_ids: string[] }[])
    : [];
  return (
    <div className="flex flex-col gap-4">
      <div className={ui.card}>
        <div className="mb-3 flex flex-wrap gap-4 text-sm">
          <span>
            {t("detail.carddav.mirroredContacts")}: <strong>{String(facts.mirrored_contacts ?? 0)}</strong>
          </span>
          <span>
            {t("detail.carddav.shareWithEmail")}: <strong>{shareText(facts.share_with_email)}</strong>
          </span>
          <span>
            {t("detail.carddav.shareWithPhone")}: <strong>{shareText(facts.share_with_phone)}</strong>
          </span>
          <span>
            {t("detail.carddav.shareWithAddress")}: <strong>{shareText(facts.share_with_address)}</strong>
          </span>
        </div>
        <table className={ui.table}>
          <thead>
            <tr>
              <th>{t("detail.carddav.columns.field")}</th>
              <th>{t("detail.carddav.columns.count")}</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(usage).map(([field, count]) => (
              <tr key={field}>
                <td>{field}</td>
                <td>{count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {duplicates.length > 0 ? (
        <div className={ui.card}>
          <h3 className={ui.h2}>{t("detail.carddav.duplicateCandidates")}</h3>
          <ul className="list-inside list-disc text-sm">
            {duplicates.map((d) => (
              <li key={d.email}>{d.email}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function CaldavFacts({ facts, t }: { facts: Record<string, unknown>; t: ReturnType<typeof useTranslations> }) {
  const usage = (facts.field_usage as Record<string, number>) ?? {};
  const months = (facts.events_per_month as Record<string, number>) ?? {};
  const prefixes = Array.isArray(facts.top_summary_prefixes)
    ? (facts.top_summary_prefixes as { prefix: string; count: number }[])
    : [];
  return (
    <div className="flex flex-col gap-4">
      <div className={ui.card}>
        <div className="mb-3 flex flex-wrap gap-4 text-sm">
          <span>
            {t("detail.caldav.mirroredEvents")}: <strong>{String(facts.mirrored_events ?? 0)}</strong>
          </span>
          <span>
            {t("detail.caldav.allDayShare")}: <strong>{shareText(facts.all_day_share)}</strong>
          </span>
        </div>
        <table className={ui.table}>
          <thead>
            <tr>
              <th>{t("detail.caldav.columns.field")}</th>
              <th>{t("detail.caldav.columns.count")}</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(usage).map(([field, count]) => (
              <tr key={field}>
                <td>{field}</td>
                <td>{count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className={ui.card}>
        <h3 className={ui.h2}>{t("detail.caldav.eventsPerMonth")}</h3>
        <table className={ui.table}>
          <thead>
            <tr>
              <th>{t("detail.caldav.columns.month")}</th>
              <th>{t("detail.caldav.columns.count")}</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(months).map(([month, count]) => (
              <tr key={month}>
                <td>{month}</td>
                <td>{count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {prefixes.length > 0 ? (
        <div className={ui.card}>
          <h3 className={ui.h2}>{t("detail.caldav.topPrefixes")}</h3>
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("detail.caldav.columns.prefix")}</th>
                <th>{t("detail.caldav.columns.count")}</th>
              </tr>
            </thead>
            <tbody>
              {prefixes.map((p) => (
                <tr key={p.prefix}>
                  <td>{p.prefix}</td>
                  <td>{p.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
