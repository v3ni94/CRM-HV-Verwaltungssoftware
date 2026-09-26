import { getTranslations } from "next-intl/server";

import { PageHeader } from "@/components/ui/PageHeader";
import { DeadlinesTable, type Deadline } from "@/components/workspace/DeadlinesTable";
import { JobSettingsForm, type JobSettings } from "@/components/workspace/JobSettingsForm";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type SearchParams = Record<string, string | undefined>;
const KINDS = ["contract_end", "contract_termination", "meter_calibration", "bank_consent", "document_retention_end", "meeting_resolution_deadline"];
const STATUSES = ["open", "done", "all"];

/** Fristenliste (A41): GET /api/v1/workspace/deadlines mit Filter Typ, Status, Zeitraum.
 *  Orientierung, keine rechtliche Fristberechnung (M1-09); die Vorfrist kommt aus den
 *  Einstellungen der Tagesjobs (Vorschlag 30 Tage). */
export default async function DeadlinesPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const t = await getTranslations("Deadlines");
  const params = await searchParams;
  const kind = params.kind && KINDS.includes(params.kind) ? params.kind : "";
  const status = params.status && STATUSES.includes(params.status) ? params.status : "open";
  const query = new URLSearchParams({ status });
  if (kind) query.set("kind", kind);
  if (params.from) query.set("from", params.from);
  if (params.to) query.set("to", params.to);

  const [me, response, settingsResponse] = await Promise.all([
    serverApi().GET("/api/v1/auth/me"),
    serverFetch(`/api/v1/workspace/deadlines?${query.toString()}`),
    serverFetch("/api/v1/workspace/job-settings"),
  ]);
  redirectIfUnauthenticated(response);
  const rows = response.ok ? ((await response.json()) as Deadline[]) : null;
  const settings = settingsResponse.ok ? ((await settingsResponse.json()) as JobSettings) : null;
  const canManage = me.data?.permissions.includes("tenant_settings:update") ?? false;

  return (
    <div className={ui.pageGap}>
      <PageHeader eyebrow={t("toCheck")} title={t("title")} description={t("description")} />
      <form method="get" className={`${ui.card} grid grid-cols-2 gap-3 md:grid-cols-5`} aria-label={t("filter.apply")}>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("filter.kind")}</span>
          <select name="kind" defaultValue={kind} className={ui.input}>
            <option value="">{t("filter.allKinds")}</option>
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {t(`kind.${k}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("filter.status")}</span>
          <select name="status" defaultValue={status} className={ui.input}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`status.${s}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("filter.from")}</span>
          <input type="date" name="from" defaultValue={params.from ?? ""} className={ui.input} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("filter.to")}</span>
          <input type="date" name="to" defaultValue={params.to ?? ""} className={ui.input} />
        </label>
        <div className="flex items-end">
          <button type="submit" className={ui.button}>
            {t("filter.apply")}
          </button>
        </div>
      </form>
      {rows === null ? (
        <p role="alert" className={ui.alert}>
          {t("loadError")}
        </p>
      ) : (
        <DeadlinesTable rows={rows} />
      )}
      {canManage && settings ? <JobSettingsForm initial={settings} /> : null}
    </div>
  );
}
