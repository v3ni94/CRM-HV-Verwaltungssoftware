"use client";

import { useCallback, useEffect, useState } from "react";

import { useTranslations } from "next-intl";

import { StatusPill, type StatusPillVariant } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Postausgang (M23-01): Postaufträge je Zustellung mit Anbieterstatus, Filter, manueller
 *  Erfassung (Druck, Versand, Zugang mit Nachweis), Statusabruf und Stornierung; für
 *  Administratoren die Anbietereinstellung des Mandanten (Standard: manuelle Postausgangsliste). */

export type PostalJob = {
  id: string;
  dispatch_id: string;
  document_id: string;
  contact_id: string;
  dunning_case_id: string | null;
  provider: string;
  provider_job_id: string | null;
  status: "submitted" | "printed" | "sent" | "delivered" | "failed" | "cancelled";
  options: { registered?: string | null; color?: boolean; duplex?: boolean };
  recipient_address: string;
  filename: string | null;
  pages: number | null;
  price: string | null;
  tracking_code: string | null;
  tracking_status: string | null;
  error: string | null;
  submitted_at: string | null;
  last_polled_at: string | null;
  completed_at: string | null;
  created_at: string;
  events?: { id: string; status: string; source: string; detail: string | null; occurred_at: string }[];
};

export type PostalSettings = {
  provider: string;
  enabled: boolean;
  username: string | null;
  has_api_key: boolean;
  mode: "test" | "live";
  default_color: boolean;
  default_duplex: boolean;
  default_registered: string | null;
  last_balance: string | null;
  last_checked_at: string | null;
  last_error: string | null;
  providers: string[];
};

const VARIANT: Record<PostalJob["status"], StatusPillVariant> = {
  submitted: "neutral",
  printed: "neutral",
  sent: "warning",
  delivered: "success",
  failed: "danger",
  cancelled: "neutral",
};

const OPEN = new Set(["submitted", "printed", "sent"]);

type ManualForm = {
  status: "printed" | "sent" | "delivered" | "failed";
  occurred_at: string;
  evidence_kind: string;
  evidence_ref: string;
  note: string;
};

const EMPTY_MANUAL: ManualForm = { status: "sent", occurred_at: "", evidence_kind: "", evidence_ref: "", note: "" };

export function PostalOutbox({
  canWrite,
  canSettings,
  initialJobs,
  initialSettings,
}: {
  canWrite: boolean;
  canSettings: boolean;
  initialJobs?: PostalJob[];
  initialSettings?: PostalSettings | null;
}) {
  const t = useTranslations("PostalOutbox");
  const [jobs, setJobs] = useState<PostalJob[]>(initialJobs ?? []);
  const [loading, setLoading] = useState(initialJobs === undefined);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("open");
  const [provider, setProvider] = useState<string>("");
  const [dunningOnly, setDunningOnly] = useState(false);
  const [selected, setSelected] = useState<PostalJob | null>(null);
  const [manual, setManual] = useState<ManualForm>(EMPTY_MANUAL);
  const [settings, setSettings] = useState<PostalSettings | null>(initialSettings ?? null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (provider) params.set("provider", provider);
    if (dunningOnly) params.set("dunning_only", "true");
    const res = await bff<PostalJob[]>(`/api/bff/postal/jobs?${params.toString()}`);
    if (res.ok) {
      setJobs(res.data ?? []);
      setError(null);
    } else setError(res.message);
    setLoading(false);
  }, [status, provider, dunningOnly]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!canSettings || settings) return;
    void bff<PostalSettings>("/api/bff/postal/settings").then((res) => {
      if (res.ok) setSettings(res.data);
    });
  }, [canSettings, settings]);

  async function openJob(job: PostalJob) {
    const res = await bff<PostalJob>(`/api/bff/postal/jobs/${job.id}`);
    setSelected(res.ok ? res.data : job);
    setManual(EMPTY_MANUAL);
  }

  function replace(job: PostalJob) {
    setJobs((list) => list.map((j) => (j.id === job.id ? { ...j, ...job } : j)));
    setSelected((s) => (s && s.id === job.id ? { ...s, ...job } : s));
  }

  async function submitManual() {
    if (!selected) return;
    const body: Record<string, unknown> = { status: manual.status };
    if (manual.occurred_at) body.occurred_at = new Date(manual.occurred_at).toISOString();
    if (manual.evidence_kind) body.evidence_kind = manual.evidence_kind;
    if (manual.evidence_ref) body.evidence_ref = manual.evidence_ref;
    if (manual.note) body.note = manual.note;
    const res = await bff<PostalJob>(`/api/bff/postal/jobs/${selected.id}/manual`, { method: "POST", body: JSON.stringify(body) });
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setError(null);
    replace(res.data);
    await openJob(res.data);
  }

  async function action(job: PostalJob, kind: "refresh" | "cancel") {
    if (kind === "cancel" && !window.confirm(t("confirmCancel"))) return;
    const res = await bff<PostalJob>(`/api/bff/postal/jobs/${job.id}/${kind}`, { method: "POST" });
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setError(null);
    replace(res.data);
  }

  return (
    <div className={ui.sectionGap}>
      {error ? <div className={ui.alert}>{error}</div> : null}
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("filterStatus")}</span>
          <select className={ui.input} value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="open">{t("statusOpen")}</option>
            <option value="">{t("statusAll")}</option>
            {(["submitted", "printed", "sent", "delivered", "failed", "cancelled"] as const).map((s) => (
              <option key={s} value={s}>
                {t(`status.${s}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("filterProvider")}</span>
          <select className={ui.input} value={provider} onChange={(e) => setProvider(e.target.value)}>
            <option value="">{t("statusAll")}</option>
            <option value="manual">{t("provider.manual")}</option>
            <option value="letterxpress">{t("provider.letterxpress")}</option>
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={dunningOnly} onChange={(e) => setDunningOnly(e.target.checked)} />
          {t("filterDunning")}
        </label>
        <button type="button" className={ui.secondary} onClick={() => void load()}>
          {t("reload")}
        </button>
        {canSettings ? (
          <button type="button" className={ui.secondary} onClick={() => setSettingsOpen((v) => !v)}>
            {t("settings.title")}
          </button>
        ) : null}
      </div>

      {canSettings && settingsOpen && settings ? (
        <PostalSettingsPanel settings={settings} onChange={setSettings} />
      ) : null}

      <div className={ui.card}>
        {loading ? (
          <p className={ui.small}>{t("loading")}</p>
        ) : jobs.length === 0 ? (
          <p className={ui.small}>{t("empty")}</p>
        ) : (
          <div className={ui.tableScroll}>
            <table className={ui.table}>
              <thead>
                <tr>
                  <th>{t("colRecipient")}</th>
                  <th>{t("colDocument")}</th>
                  <th>{t("colProvider")}</th>
                  <th>{t("colStatus")}</th>
                  <th>{t("colTracking")}</th>
                  <th>{t("colCreated")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id}>
                    <td className="whitespace-pre-line align-top">{job.recipient_address}</td>
                    <td className="align-top">
                      {job.filename ?? job.document_id}
                      {job.dunning_case_id ? <span className={`${ui.badge} ml-2`}>{t("dunning")}</span> : null}
                      {job.options.registered ? <span className={`${ui.badge} ml-2`}>{t(`registered.${job.options.registered}`)}</span> : null}
                    </td>
                    <td className="align-top">
                      {t(`provider.${job.provider}` as "provider.manual")}
                      {job.provider_job_id && job.provider !== "manual" ? <div className={ui.small}>{job.provider_job_id}</div> : null}
                    </td>
                    <td className="align-top">
                      <StatusPill label={t(`status.${job.status}`)} variant={VARIANT[job.status]} />
                      {job.error ? <div className={ui.error}>{job.error}</div> : null}
                    </td>
                    <td className="align-top">
                      {job.tracking_code ?? ""}
                      {job.tracking_status ? <div className={ui.small}>{job.tracking_status}</div> : null}
                    </td>
                    <td className="align-top">{formatDateTime(job.submitted_at ?? job.created_at)}</td>
                    <td className="align-top">
                      <div className="flex flex-wrap gap-1">
                        <button type="button" className={ui.buttonSm} onClick={() => void openJob(job)}>
                          {t("details")}
                        </button>
                        {canWrite && job.provider !== "manual" && OPEN.has(job.status) ? (
                          <button type="button" className={ui.buttonSm} onClick={() => void action(job, "refresh")}>
                            {t("refresh")}
                          </button>
                        ) : null}
                        {canWrite && OPEN.has(job.status) ? (
                          <button type="button" className={ui.buttonSm} onClick={() => void action(job, "cancel")}>
                            {t("cancel")}
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selected ? (
        <div className={ui.card}>
          <div className="flex items-start justify-between gap-3">
            <h2 className={ui.title}>{t("detailTitle")}</h2>
            <button type="button" className={ui.buttonSm} onClick={() => setSelected(null)}>
              {t("close")}
            </button>
          </div>
          <p className="whitespace-pre-line text-sm">{selected.recipient_address}</p>
          <p className={ui.small}>
            {t(`provider.${selected.provider}` as "provider.manual")}
            {selected.provider_job_id ? `, ${selected.provider_job_id}` : ""}
            {selected.pages != null ? `, ${t("pages", { count: selected.pages })}` : ""}
          </p>
          <h3 className={`${ui.subtitle} mt-3`}>{t("history")}</h3>
          <ul className="text-sm">
            {(selected.events ?? []).map((e) => (
              <li key={e.id}>
                {formatDateTime(e.occurred_at)}: {t(`status.${e.status}` as "status.sent")} ({t(`source.${e.source}` as "source.manual")}){e.detail ? `, ${e.detail}` : ""}
              </li>
            ))}
          </ul>
          {canWrite && selected.status !== "delivered" && selected.status !== "cancelled" ? (
            <form
              className="mt-4 flex flex-col gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                void submitManual();
              }}
            >
              <h3 className={ui.subtitle}>{t("manual.title")}</h3>
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("manual.status")}</span>
                <select className={ui.input} value={manual.status} onChange={(e) => setManual({ ...manual, status: e.target.value as ManualForm["status"] })}>
                  {(["printed", "sent", "delivered", "failed"] as const).map((s) => (
                    <option key={s} value={s}>
                      {t(`status.${s}`)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("manual.occurredAt")}</span>
                <input type="datetime-local" className={ui.input} value={manual.occurred_at} onChange={(e) => setManual({ ...manual, occurred_at: e.target.value })} />
              </label>
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("manual.evidenceKind")}</span>
                <select className={ui.input} value={manual.evidence_kind} onChange={(e) => setManual({ ...manual, evidence_kind: e.target.value })}>
                  <option value="">{t("manual.none")}</option>
                  {(["registered_mail", "courier", "hand_delivery", "other"] as const).map((k) => (
                    <option key={k} value={k}>
                      {t(`evidence.${k}`)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("manual.evidenceRef")}</span>
                <input className={ui.input} value={manual.evidence_ref} onChange={(e) => setManual({ ...manual, evidence_ref: e.target.value })} />
              </label>
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("manual.note")}</span>
                <input className={ui.input} value={manual.note} onChange={(e) => setManual({ ...manual, note: e.target.value })} />
              </label>
              <p className={ui.help}>{t("manual.help")}</p>
              <div className={ui.formActions}>
                <button type="submit" className={ui.primary}>
                  {t("manual.save")}
                </button>
              </div>
            </form>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function PostalSettingsPanel({ settings, onChange }: { settings: PostalSettings; onChange: (s: PostalSettings) => void }) {
  const t = useTranslations("PostalOutbox.settings");
  const [form, setForm] = useState({
    provider: settings.provider,
    enabled: settings.enabled,
    username: settings.username ?? "",
    api_key: "",
    mode: settings.mode,
    default_color: settings.default_color,
    default_duplex: settings.default_duplex,
    default_registered: settings.default_registered ?? "",
  });
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    const body: Record<string, unknown> = {
      provider: form.provider,
      enabled: form.enabled,
      username: form.username || null,
      mode: form.mode,
      default_color: form.default_color,
      default_duplex: form.default_duplex,
      default_registered: form.default_registered || null,
    };
    if (form.api_key) body.api_key = form.api_key;
    const res = await bff<PostalSettings>("/api/bff/postal/settings", { method: "PUT", body: JSON.stringify(body) });
    if (!res.ok) {
      setError(res.message);
      setMessage(null);
      return;
    }
    setError(null);
    setMessage(t("saved"));
    setForm({ ...form, api_key: "" });
    onChange(res.data);
  }

  async function test() {
    const res = await bff<PostalSettings>("/api/bff/postal/settings/test", { method: "POST" });
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setError(null);
    onChange(res.data);
    setMessage(res.data.last_error ? `${t("testFailed")}: ${res.data.last_error}` : t("testOk", { balance: res.data.last_balance ?? "" }));
  }

  return (
    <form
      className={`${ui.card} flex flex-col gap-3`}
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <h2 className={ui.title}>{t("title")}</h2>
      <p className={ui.help}>{t("intro")}</p>
      {error ? <div className={ui.alert}>{error}</div> : null}
      {message ? <div className={ui.success}>{message}</div> : null}
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("provider")}</span>
        <select className={ui.input} value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value })}>
          {settings.providers.map((p) => (
            <option key={p} value={p}>
              {p === "manual" ? t("providerManual") : p === "letterxpress" ? t("providerLetterxpress") : p}
            </option>
          ))}
        </select>
      </label>
      {form.provider !== "manual" ? (
        <>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("username")}</span>
            <input className={ui.input} value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} autoComplete="off" />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{settings.has_api_key ? t("apiKeyReplace") : t("apiKey")}</span>
            <input type="password" className={ui.input} value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} autoComplete="new-password" />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("mode")}</span>
            <select className={ui.input} value={form.mode} onChange={(e) => setForm({ ...form, mode: e.target.value as "test" | "live" })}>
              <option value="test">{t("modeTest")}</option>
              <option value="live">{t("modeLive")}</option>
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
            {t("enabled")}
          </label>
          <p className={ui.help}>{t("enabledHelp")}</p>
        </>
      ) : null}
      <div className="flex flex-wrap gap-4">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.default_color} onChange={(e) => setForm({ ...form, default_color: e.target.checked })} />
          {t("color")}
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.default_duplex} onChange={(e) => setForm({ ...form, default_duplex: e.target.checked })} />
          {t("duplex")}
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("registered")}</span>
          <select className={ui.input} value={form.default_registered} onChange={(e) => setForm({ ...form, default_registered: e.target.value })}>
            <option value="">{t("registeredNone")}</option>
            <option value="r1">{t("registeredR1")}</option>
            <option value="r2">{t("registeredR2")}</option>
          </select>
        </label>
      </div>
      {settings.last_checked_at ? (
        <p className={ui.small}>
          {t("lastChecked", { at: formatDateTime(settings.last_checked_at) })}
          {settings.last_balance != null ? `, ${t("balance", { balance: settings.last_balance })}` : ""}
          {settings.last_error ? `, ${settings.last_error}` : ""}
        </p>
      ) : null}
      <div className={ui.formActions}>
        <button type="submit" className={ui.primary}>
          {t("save")}
        </button>
        {form.provider !== "manual" ? (
          <button type="button" className={ui.secondary} onClick={() => void test()}>
            {t("test")}
          </button>
        ) : null}
      </div>
    </form>
  );
}
