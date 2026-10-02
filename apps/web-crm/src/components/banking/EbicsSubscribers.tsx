"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { StatusPill, type StatusPillVariant } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { formatDate, formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

/** EBICS-Grundgerüst (M11-01, AE23, Regel M11-11): Mandantenschalter, Teilnehmer, Schlüssel,
 *  INI/HIA, Freischaltung, HPB mit Prüfung durch eine zweite Person, Abruf C53. Die
 *  Übertragung zur Bank fehlt, bis eine geprüfte Implementierung installiert ist (AE23-01);
 *  die API meldet dann MHVP-BANK-0050. Keine Zahlung, G2 bleibt geschlossen. */

export type EbicsStatus = {
  enabled: boolean;
  signature_key_mode: "external" | "server";
  transport_available: boolean;
  transport: string;
  min_key_bits: number;
  default_key_bits: number;
  key_bits_strict_from: string;
  c53_btf: string;
  open_questions: string[];
};

export type EbicsKey = {
  id: string;
  owner: "subscriber" | "bank";
  usage: "signature" | "authentication" | "encryption";
  version: string;
  key_bits: number;
  source: string;
  public_key_sha256: string;
  letter_hash: string | null;
  has_private_key: boolean;
  runs_out: string | null;
};

export type EbicsOrder = {
  id: string;
  order_type: string;
  status: string;
  error_code: string | null;
  error_detail: string | null;
  result: Record<string, unknown>;
  created_at: string;
};

export type EbicsSubscriber = {
  id: string;
  label: string;
  host_id: string;
  partner_id: string;
  ebics_user_id: string;
  url: string;
  ebics_version: string;
  signature_version: string;
  key_bits: number;
  signature_key_mode: "external" | "server";
  status: string;
  next_step: string;
  ini_sent_at: string | null;
  hia_sent_at: string | null;
  activated_on: string | null;
  bank_keys_verified_at: string | null;
  last_download_at: string | null;
  keys: EbicsKey[];
  orders?: EbicsOrder[];
};

const STATUS_VARIANT: Record<string, StatusPillVariant> = {
  created: "neutral",
  keys_ready: "warning",
  initialised: "warning",
  activated: "warning",
  bank_keys_received: "warning",
  ready: "success",
  suspended: "danger",
};

const BASE = "/api/bff/banking/ebics";

export function EbicsSubscribers() {
  const t = useTranslations("Ebics");
  const [status, setStatus] = useState<EbicsStatus | null>(null);
  const [subscribers, setSubscribers] = useState<EbicsSubscriber[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [s, list] = await Promise.all([
      bff<EbicsStatus>(`${BASE}/status`),
      bff<EbicsSubscriber[]>(`${BASE}/subscribers`),
    ]);
    if (s.ok) setStatus(s.data);
    if (list.ok) setSubscribers(list.data);
    if (!s.ok) setError(s.message);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function call(path: string, body?: unknown, method = "POST", done?: string) {
    setError(null);
    setNotice(null);
    const result = await bff<unknown>(`${BASE}${path}`, {
      method,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!result.ok) {
      setError(result.message);
      return false;
    }
    if (done) setNotice(done);
    await load();
    return true;
  }

  if (!status) return null;
  return (
    <section className={ui.card} aria-labelledby="ebics-title">
      <h2 id="ebics-title" className={ui.title}>
        {t("title")}
      </h2>
      <p className={`${ui.notice} mt-2`}>{t("intro")}</p>
      {!status.transport_available && <p className={`${ui.alert} mt-2`}>{t("transportMissing")}</p>}
      <p className={`${ui.help} mt-2`}>
        {t("keyPolicy", {
          min: status.min_key_bits,
          standard: status.default_key_bits,
          date: formatDate(status.key_bits_strict_from),
        })}
      </p>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <StatusPill label={status.enabled ? t("enabled") : t("disabled")} variant={status.enabled ? "success" : "neutral"} />
        <button
          type="button"
          className={ui.button}
          onClick={() => void call("/settings", { enabled: !status.enabled }, "PUT")}
        >
          {status.enabled ? t("switchOff") : t("switchOn")}
        </button>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("signatureMode")}</span>
          <select
            className={ui.input}
            value={status.signature_key_mode}
            onChange={(e) => void call("/settings", { signature_key_mode: e.target.value }, "PUT")}
          >
            <option value="external">{t("modeExternal")}</option>
            <option value="server">{t("modeServer")}</option>
          </select>
        </label>
      </div>
      <p className={`${ui.help} mt-1`}>{t("modeHelp")}</p>
      {error && (
        <p role="alert" className={`${ui.alert} mt-3`}>
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className={`${ui.success} mt-3`}>
          {notice}
        </p>
      )}
      <ul className="mt-4 flex flex-col gap-3">
        {subscribers.map((s) => (
          <SubscriberRow key={s.id} subscriber={s} call={call} />
        ))}
      </ul>
      {subscribers.length === 0 && <p className={`${ui.help} mt-3`}>{t("empty")}</p>}
      {status.enabled && <CreateForm call={call} defaultBits={status.default_key_bits} />}
    </section>
  );
}

type Call = (path: string, body?: unknown, method?: string, done?: string) => Promise<boolean>;

function CreateForm({ call, defaultBits }: { call: Call; defaultBits: number }) {
  const t = useTranslations("Ebics");
  const [form, setForm] = useState({
    label: "",
    host_id: "",
    partner_id: "",
    ebics_user_id: "",
    url: "https://",
    ebics_version: "3.0",
    signature_version: "A006",
    key_bits: String(defaultBits),
  });
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm({ ...form, [key]: e.target.value });
  const fields: [keyof typeof form, string][] = [
    ["label", t("label")],
    ["host_id", t("hostId")],
    ["partner_id", t("partnerId")],
    ["ebics_user_id", t("userId")],
    ["url", t("url")],
  ];
  return (
    <form
      className="mt-4 grid gap-3 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        void call("/subscribers", { ...form, key_bits: Number(form.key_bits) }, "POST", t("created"));
      }}
    >
      <h3 className={`${ui.subtitle} sm:col-span-2`}>{t("createTitle")}</h3>
      {fields.map(([key, label]) => (
        <label key={key} className="flex flex-col gap-1">
          <span className={ui.label}>{label}</span>
          <input className={ui.input} value={form[key]} onChange={set(key)} required />
        </label>
      ))}
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("version")}</span>
        <select className={ui.input} value={form.ebics_version} onChange={set("ebics_version")}>
          <option value="3.0">3.0</option>
          <option value="2.5">2.5</option>
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("signatureVersion")}</span>
        <select className={ui.input} value={form.signature_version} onChange={set("signature_version")}>
          <option value="A006">A006</option>
          <option value="A005">A005</option>
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("keyBits")}</span>
        <select className={ui.input} value={form.key_bits} onChange={set("key_bits")}>
          <option value="4096">4096</option>
          <option value="3072">3072</option>
          <option value="2048">2048</option>
        </select>
      </label>
      <div className="sm:col-span-2">
        <button type="submit" className={ui.primary}>
          {t("create")}
        </button>
      </div>
    </form>
  );
}

function SubscriberRow({ subscriber: s, call }: { subscriber: EbicsSubscriber; call: Call }) {
  const t = useTranslations("Ebics");
  const [text, setText] = useState("");
  const [second, setSecond] = useState("");
  const [day, setDay] = useState("");
  const [until, setUntil] = useState("");
  const path = `/subscribers/${s.id}`;
  const subscriberKeys = s.keys.filter((k) => k.owner === "subscriber");
  const expiring = subscriberKeys.find((k) => k.runs_out);
  const step = s.next_step;
  return (
    <li className="rounded-md border border-border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{s.label}</span>
        <StatusPill label={t(`status.${s.status}`)} variant={STATUS_VARIANT[s.status] ?? "neutral"} />
        <span className={ui.help}>
          {t("ids", { host: s.host_id, partner: s.partner_id, user: s.ebics_user_id, version: s.ebics_version })}
        </span>
      </div>
      <p className={`${ui.help} mt-1`}>
        {t("keysLine", { count: subscriberKeys.length, bits: s.key_bits, mode: t(s.signature_key_mode === "server" ? "modeServer" : "modeExternal") })}
      </p>
      {subscriberKeys.length > 0 && (
        <p className="mt-1">
          <a className={ui.buttonSm} href={`/api/bff/banking/ebics${path}/letters.pdf`} download data-testid="ebics-letter-pdf">
            {t("letterPdf")}
          </a>
        </p>
      )}
      {expiring?.runs_out && <p className={`${ui.help} mt-1`}>{t("runsOut", { date: formatDate(expiring.runs_out) })}</p>}
      {s.last_download_at && <p className={`${ui.help} mt-1`}>{t("lastDownload", { at: formatDateTime(s.last_download_at) })}</p>}
      {step !== "none" && <p className="mt-2 text-sm">{t(`step.${step}`)}</p>}
      <div className="mt-2 flex flex-wrap items-end gap-2">
        {step === "generate_keys" && (
          <button type="button" className={ui.primary} onClick={() => void call(`${path}/keys`, {}, "POST", t("done"))}>
            {t("generateKeys")}
          </button>
        )}
        {step === "upload_signature_key_or_confirm_ini" && (
          <>
            <label className="flex w-full flex-col gap-1">
              <span className={ui.label}>{t("publicKeyOrNote")}</span>
              <textarea className={ui.input} rows={3} value={text} onChange={(e) => setText(e.target.value)} />
            </label>
            <button type="button" className={ui.button} onClick={() => void call(`${path}/signature-key`, { public_key_pem: text }, "POST", t("done"))}>
              {t("uploadKey")}
            </button>
            <button type="button" className={ui.button} onClick={() => void call(`${path}/ini/external`, { note: text }, "POST", t("done"))}>
              {t("confirmIniExternal")}
            </button>
          </>
        )}
        {step === "send_ini" && (
          <button type="button" className={ui.primary} onClick={() => void call(`${path}/ini`, undefined, "POST", t("done"))}>
            {t("sendIni")}
          </button>
        )}
        {step === "send_hia" && (
          <button type="button" className={ui.primary} onClick={() => void call(`${path}/hia`, undefined, "POST", t("done"))}>
            {t("sendHia")}
          </button>
        )}
        {step === "confirm_activation" && (
          <>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("activatedOn")}</span>
              <input type="date" className={ui.input} value={day} onChange={(e) => setDay(e.target.value)} />
            </label>
            <button type="button" className={ui.primary} onClick={() => void call(`${path}/activation`, { activated_on: day }, "POST", t("done"))}>
              {t("confirmActivation")}
            </button>
          </>
        )}
        {step === "fetch_bank_keys" && (
          <button type="button" className={ui.primary} onClick={() => void call(`${path}/hpb`, undefined, "POST", t("done"))}>
            {t("fetchBankKeys")}
          </button>
        )}
        {step === "verify_bank_keys" && (
          <>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("authHash")}</span>
              <input className={ui.input} value={text} onChange={(e) => setText(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("encHash")}</span>
              <input className={ui.input} value={second} onChange={(e) => setSecond(e.target.value)} />
            </label>
            <button
              type="button"
              className={ui.primary}
              onClick={() =>
                void call(`${path}/bank-keys/verify`, { authentication_hash: text, encryption_hash: second }, "POST", t("done"))
              }
            >
              {t("verify")}
            </button>
          </>
        )}
        {step === "download_statements" && (
          <>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("dateFrom")}</span>
              <input type="date" className={ui.input} value={day} onChange={(e) => setDay(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("dateTo")}</span>
              <input type="date" className={ui.input} value={until} onChange={(e) => setUntil(e.target.value)} />
            </label>
            <button
              type="button"
              className={ui.primary}
              onClick={() =>
                void call(`${path}/statements`, { date_from: day || null, date_to: until || null }, "POST", t("downloaded"))
              }
            >
              {t("download")}
            </button>
          </>
        )}
      </div>
      {s.status !== "suspended" && (
        <details className="mt-2">
          <summary className={`${ui.help} cursor-pointer`}>{t("more")}</summary>
          <div className="mt-2 flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("reason")}</span>
              <input className={ui.input} value={second} onChange={(e) => setSecond(e.target.value)} />
            </label>
            {subscriberKeys.length > 0 && (
              <button type="button" className={ui.button} onClick={() => void call(`${path}/keys`, { reason: second }, "POST", t("done"))}>
                {t("rotate")}
              </button>
            )}
            <button type="button" className={ui.danger} onClick={() => void call(`${path}/suspend`, { reason: second }, "POST", t("done"))}>
              {t("suspend")}
            </button>
          </div>
        </details>
      )}
    </li>
  );
}
