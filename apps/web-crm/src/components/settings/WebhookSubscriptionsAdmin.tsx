"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { StatusPill, type StatusPillVariant } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Outgoing webhook subscriptions (section 12, A69): list with last delivery, create (https
 *  only, event types from the catalogue, secret shown once), activate/deactivate, delete with
 *  confirmation, delivery log (last 20) with manual redelivery. The API offers no test
 *  delivery, so none is offered here. */
export type WebhookSubscription = {
  id: string;
  url: string;
  event_types: string[];
  active: boolean;
  description: string | null;
  created_at?: string | null;
  last_delivery_status?: string | null;
  last_delivery_status_code?: number | null;
  last_delivery_at?: string | null;
};

export type WebhookEventType = { type: string; description: string };

export type WebhookDelivery = {
  id: string;
  event_id: string;
  status: string;
  attempts: number;
  next_attempt_at: string | null;
  last_status_code: number | null;
  last_error: string | null;
  delivered_at: string | null;
};

type Created = WebhookSubscription & { secret: string };

const LOG_SIZE = 20;

function statusVariant(status: string | null | undefined): StatusPillVariant {
  if (status === "succeeded") return "success";
  if (status === "failed") return "danger";
  if (status === "pending") return "warning";
  return "neutral";
}

export function WebhookSubscriptionsAdmin({
  initial,
  eventTypes,
  loadFailed = false,
  canManage,
  canDelete,
}: {
  initial: WebhookSubscription[];
  eventTypes: WebhookEventType[];
  loadFailed?: boolean;
  canManage: boolean;
  canDelete: boolean;
}) {
  const t = useTranslations("Webhooks");
  const [hooks, setHooks] = useState(initial);
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<Created | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [openLog, setOpenLog] = useState<string | null>(null);
  const [logs, setLogs] = useState<Record<string, WebhookDelivery[]>>({});
  const [busy, setBusy] = useState(false);

  const statusLabel = (status: string | null | undefined) =>
    status === "succeeded" || status === "failed" || status === "pending" ? t(`status.${status}`) : t("list.none");

  async function loadLog(hookId: string) {
    setError(null);
    const res = await bff<WebhookDelivery[]>(`/api/bff/tenant/webhooks/${hookId}/deliveries?page=1&page_size=${LOG_SIZE}`);
    if (res.ok) setLogs((prev) => ({ ...prev, [hookId]: res.data }));
    else setError(t("log.loadError"));
  }

  async function toggleLog(hookId: string) {
    if (openLog === hookId) {
      setOpenLog(null);
      return;
    }
    setOpenLog(hookId);
    await loadLog(hookId);
  }

  async function toggleActive(hook: WebhookSubscription) {
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<WebhookSubscription>(`/api/bff/tenant/webhooks/${hook.id}`, {
      method: "PATCH",
      body: JSON.stringify({ active: !hook.active }),
    });
    setBusy(false);
    if (res.ok) setHooks((prev) => prev.map((x) => (x.id === hook.id ? { ...x, ...res.data } : x)));
    else setError(res.message);
  }

  async function remove(hook: WebhookSubscription) {
    if (!window.confirm(t("list.deleteConfirm"))) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<null>(`/api/bff/tenant/webhooks/${hook.id}`, { method: "DELETE" });
    setBusy(false);
    if (res.ok) {
      setHooks((prev) => prev.filter((x) => x.id !== hook.id));
      if (openLog === hook.id) setOpenLog(null);
    } else setError(res.message);
  }

  async function redeliver(hookId: string, delivery: WebhookDelivery) {
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<null>(`/api/bff/tenant/webhook-deliveries/${delivery.id}/redeliver`, { method: "POST" });
    setBusy(false);
    if (res.ok) {
      setMessage(t("log.redelivered"));
      await loadLog(hookId);
    } else setError(res.message);
  }

  async function copySecret(secret: string) {
    try {
      await navigator.clipboard.writeText(secret);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="flex min-w-0 flex-col gap-4">
      {canManage ? (
        creating ? (
          <CreateForm
            eventTypes={eventTypes}
            onCancel={() => setCreating(false)}
            onCreated={(hook) => {
              const rest: WebhookSubscription = { ...hook };
              delete (rest as Partial<Created>).secret;
              setHooks((prev) => [...prev, rest]);
              setCreated(hook);
              setCopied(false);
              setCreating(false);
            }}
          />
        ) : (
          <button type="button" className={`${ui.primary} w-fit`} onClick={() => setCreating(true)}>
            {t("newSubscription")}
          </button>
        )
      ) : (
        <p className="text-xs text-muted">{t("readOnlyHint")}</p>
      )}
      {created ? (
        <div className={`${ui.card} flex flex-col gap-2`} data-testid="webhook-secret">
          <h2 className={ui.h2}>{t("secret.title")}</h2>
          <p className={ui.help}>{t("secret.hint")}</p>
          <code className="break-all rounded bg-surface px-2 py-1 text-xs">{created.secret}</code>
          <div className={ui.formActions}>
            <button type="button" className={ui.secondary} onClick={() => copySecret(created.secret)}>
              {t("secret.copy")}
            </button>
            <button type="button" className={ui.button} onClick={() => setCreated(null)}>
              {t("secret.dismiss")}
            </button>
          </div>
          {copied ? <p className={ui.success}>{t("secret.copied")}</p> : null}
        </div>
      ) : null}
      {loadFailed ? (
        <p role="alert" className={ui.alert}>
          {t("list.loadError")}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {message ? <p className={ui.success}>{message}</p> : null}
      {hooks.length === 0 && !loadFailed ? (
        <p className="text-sm text-muted">{t("list.empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("list.url")}</th>
                <th>{t("list.eventTypes")}</th>
                <th>{t("list.active")}</th>
                <th>{t("list.lastDelivery")}</th>
                <th>{t("list.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {hooks.map((hook) => (
                <WebhookRow
                  key={hook.id}
                  hook={hook}
                  busy={busy}
                  canManage={canManage}
                  canDelete={canDelete}
                  logOpen={openLog === hook.id}
                  log={logs[hook.id]}
                  statusLabel={statusLabel}
                  onToggleLog={() => toggleLog(hook.id)}
                  onToggleActive={() => toggleActive(hook)}
                  onRemove={() => remove(hook)}
                  onRedeliver={(d) => redeliver(hook.id, d)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className={ui.help}>{t("testDelivery")}</p>
    </div>
  );
}

function WebhookRow({
  hook,
  busy,
  canManage,
  canDelete,
  logOpen,
  log,
  statusLabel,
  onToggleLog,
  onToggleActive,
  onRemove,
  onRedeliver,
}: {
  hook: WebhookSubscription;
  busy: boolean;
  canManage: boolean;
  canDelete: boolean;
  logOpen: boolean;
  log: WebhookDelivery[] | undefined;
  statusLabel: (status: string | null | undefined) => string;
  onToggleLog: () => void;
  onToggleActive: () => void;
  onRemove: () => void;
  onRedeliver: (delivery: WebhookDelivery) => void;
}) {
  const t = useTranslations("Webhooks");
  const all = hook.event_types.includes("*");
  return (
    <>
      <tr data-testid={`webhook-${hook.id}`}>
        <td className="max-w-[20rem] break-all">
          <span className="font-medium">{hook.url}</span>
          {hook.description ? <p className="text-xs text-muted">{hook.description}</p> : null}
        </td>
        <td>
          {all ? (
            <span className={ui.badge}>{t("list.all")}</span>
          ) : (
            <ul className="flex flex-col gap-0.5">
              {hook.event_types.map((type) => (
                <li key={type}>
                  <code className="text-xs">{type}</code>
                </li>
              ))}
            </ul>
          )}
        </td>
        <td>
          <StatusPill label={hook.active ? t("status.active") : t("status.inactive")} variant={hook.active ? "success" : "neutral"} />
        </td>
        <td>
          <StatusPill label={statusLabel(hook.last_delivery_status)} variant={statusVariant(hook.last_delivery_status)} />
          {hook.last_delivery_status ? (
            <p className="text-xs text-muted">
              {hook.last_delivery_status_code != null ? `HTTP ${hook.last_delivery_status_code}, ` : ""}
              {formatDateTime(hook.last_delivery_at)}
            </p>
          ) : null}
        </td>
        <td>
          <div className="flex flex-wrap gap-1">
            <button type="button" className={ui.buttonSm} onClick={onToggleLog}>
              {logOpen ? t("list.hideLog") : t("list.log")}
            </button>
            {canManage ? (
              <button type="button" className={ui.buttonSm} disabled={busy} onClick={onToggleActive}>
                {hook.active ? t("list.deactivate") : t("list.activate")}
              </button>
            ) : null}
            {canDelete ? (
              <button type="button" className={`${ui.buttonSm} text-danger-fg`} disabled={busy} onClick={onRemove}>
                {t("list.delete")}
              </button>
            ) : null}
          </div>
        </td>
      </tr>
      {logOpen ? (
        <tr data-testid={`webhook-log-${hook.id}`}>
          <td colSpan={5} className="bg-surface">
            <h3 className="mhvp-label mb-2">{t("log.title")}</h3>
            {log === undefined ? null : log.length === 0 ? (
              <p className="text-sm text-muted">{t("log.empty")}</p>
            ) : (
              <div className="overflow-x-auto">
                <table className={ui.table}>
                  <thead>
                    <tr>
                      <th>{t("log.event")}</th>
                      <th>{t("log.status")}</th>
                      <th>{t("log.code")}</th>
                      <th>{t("log.attempts")}</th>
                      <th>{t("log.nextAttempt")}</th>
                      <th>{t("log.deliveredAt")}</th>
                      <th>{t("log.error")}</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {log.map((d) => (
                      <tr key={d.id}>
                        <td>
                          <code className="text-xs">{d.event_id}</code>
                        </td>
                        <td>
                          <StatusPill label={statusLabel(d.status)} variant={statusVariant(d.status)} />
                        </td>
                        <td>{d.last_status_code ?? ""}</td>
                        <td>{d.attempts}</td>
                        <td>{formatDateTime(d.next_attempt_at)}</td>
                        <td>{formatDateTime(d.delivered_at)}</td>
                        <td className="text-xs text-muted">{d.last_error ?? ""}</td>
                        <td>
                          {canManage && d.status !== "pending" ? (
                            <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => onRedeliver(d)}>
                              {t("log.redeliver")}
                            </button>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </td>
        </tr>
      ) : null}
    </>
  );
}

function CreateForm({
  eventTypes,
  onCancel,
  onCreated,
}: {
  eventTypes: WebhookEventType[];
  onCancel: () => void;
  onCreated: (hook: Created) => void;
}) {
  const t = useTranslations("Webhooks");
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  const [all, setAll] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggleType(type: string) {
    setSelected((prev) => (prev.includes(type) ? prev.filter((x) => x !== type) : [...prev, type]));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const trimmed = url.trim();
    if (!/^https:\/\/\S+$/i.test(trimmed)) {
      setError(t("form.urlInvalid"));
      return;
    }
    const types = all ? ["*"] : selected;
    if (types.length === 0) {
      setError(t("form.eventTypesRequired"));
      return;
    }
    setBusy(true);
    const res = await bff<Created>("/api/bff/tenant/webhooks", {
      method: "POST",
      body: JSON.stringify({ url: trimmed, event_types: types, description: description.trim() || null }),
    });
    setBusy(false);
    if (res.ok) onCreated(res.data);
    else setError(res.message);
  }

  return (
    <form onSubmit={submit} className={`${ui.card} flex flex-col gap-3`} data-testid="webhook-create">
      <h2 className={ui.h2}>{t("newSubscription")}</h2>
      <div>
        <label htmlFor="webhook-url" className={ui.label}>
          {t("form.url")}
        </label>
        <input
          id="webhook-url"
          className={ui.input}
          type="url"
          inputMode="url"
          value={url}
          maxLength={2000}
          required
          disabled={busy}
          placeholder="https://"
          onChange={(e) => setUrl(e.target.value)}
        />
        <p className={ui.help}>{t("form.urlHint")}</p>
      </div>
      <div>
        <label htmlFor="webhook-description" className={ui.label}>
          {t("form.description")}
        </label>
        <input
          id="webhook-description"
          className={ui.input}
          value={description}
          maxLength={200}
          disabled={busy}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      <fieldset className="flex flex-col gap-1">
        <legend className={ui.label}>{t("form.eventTypes")}</legend>
        <p className={ui.help}>{t("form.eventTypesHint")}</p>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={all} disabled={busy} onChange={(e) => setAll(e.target.checked)} />
          {t("form.allEvents")}
        </label>
        {eventTypes.length === 0 ? <p className={ui.help}>{t("form.catalogueUnavailable")}</p> : null}
        {eventTypes.map((et) => (
          <label key={et.type} className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={all || selected.includes(et.type)}
              disabled={busy || all}
              onChange={() => toggleType(et.type)}
            />
            <span>
              <code className="text-xs">{et.type}</code>
              <span className="block text-xs text-muted">{et.description}</span>
            </span>
          </label>
        ))}
      </fieldset>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div className={ui.formActions}>
        <button type="submit" className={`${ui.primary} ${ui.actionFull}`} disabled={busy}>
          {t("create")}
        </button>
        <button type="button" className={`${ui.button} ${ui.actionFull}`} disabled={busy} onClick={onCancel}>
          {t("cancel")}
        </button>
      </div>
    </form>
  );
}
