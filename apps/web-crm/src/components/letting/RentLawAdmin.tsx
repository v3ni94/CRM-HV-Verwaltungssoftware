"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export type RentLawRule = {
  code: string;
  label: string;
  norm: string;
  value: string | null;
  unit: string;
  status: string;
  source_verified: boolean;
  source_url: string | null;
  note: string | null;
  released_at: string | null;
};

export type CapArea = {
  id: string;
  state: string;
  municipality: string;
  municipality_code: string | null;
  cap_percent: string;
  valid_from: string;
  valid_to: string | null;
  source: string;
};

const NUMBER = /^\d+([.,]\d+)?$/;
const dec = (v: string) => v.replace(",", ".");

/** One rent law parameter (M26-01): value and source check are maintained by the platform
 *  administrator; release needs a value and a source checked against the statute text. Any
 *  change resets the rule to draft (checked by the API). */
function RuleRow({ rule }: { rule: RentLawRule }) {
  const t = useTranslations("RentLaw");
  const router = useRouter();
  const [value, setValue] = useState(rule.value ?? "");
  const [verified, setVerified] = useState(rule.source_verified);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const put = async (body: Record<string, unknown>) => {
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/platform/rent-law/rules/${rule.code}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (res.ok) router.refresh();
    else setError(res.message);
  };
  const changed = value !== (rule.value ?? "") || verified !== rule.source_verified;
  return (
    <tr className="border-t align-top" data-testid={`rule-${rule.code}`}>
      <td className="py-1 pr-2">
        {rule.label}
        <div className="text-xs text-muted">
          {rule.norm}
          {rule.source_url ? (
            <>
              {" · "}
              <a className="underline" href={rule.source_url} target="_blank" rel="noreferrer">
                {t("source")}
              </a>
            </>
          ) : null}
        </div>
      </td>
      <td className="py-1 pr-2">
        <input
          className={`${ui.input} w-24`}
          aria-label={t("value", { label: rule.label })}
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />{" "}
        <span className="text-xs text-muted">{rule.unit}</span>
      </td>
      <td className="py-1 pr-2">
        <label className="flex items-center gap-1 text-sm">
          <input type="checkbox" checked={verified} onChange={(e) => setVerified(e.target.checked)} />
          {t("verified")}
        </label>
      </td>
      <td className="py-1 pr-2 text-sm">
        {rule.status === "released" ? t("released", { date: formatDate(String(rule.released_at).slice(0, 10)) }) : t("draft")}
      </td>
      <td className="py-1">
        <div className="flex flex-wrap gap-1">
          <button
            type="button"
            className={ui.button}
            disabled={busy || !changed || (value !== "" && !NUMBER.test(value))}
            onClick={() => put({ ...(value ? { value: dec(value) } : {}), source_verified: verified })}
          >
            {t("save")}
          </button>
          {rule.status === "released" ? (
            <button type="button" className={ui.button} disabled={busy} onClick={() => put({ status: "draft" })}>
              {t("withdraw")}
            </button>
          ) : (
            <button
              type="button"
              className={ui.primary}
              disabled={busy || changed || !rule.value || !rule.source_verified}
              onClick={() => put({ status: "released" })}
            >
              {t("release")}
            </button>
          )}
        </div>
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
      </td>
    </tr>
  );
}

export function RentLawRules({ rules }: { rules: RentLawRule[] }) {
  const t = useTranslations("RentLaw");
  return (
    <div className="overflow-x-auto">
<table className="w-full text-sm">
      <thead>
        <tr className="text-left text-xs text-muted">
          <th>{t("rule")}</th>
          <th>{t("valueHead")}</th>
          <th>{t("sourceHead")}</th>
          <th>{t("status")}</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {rules.map((r) => (
          <RuleRow key={r.code} rule={r} />
        ))}
      </tbody>
    </table>
</div>
  );
}

const EMPTY = { state: "NW", municipality: "", municipality_code: "", cap_percent: "15", valid_from: "", source: "" };

/** Areas with a reduced cap (state regulation). Entries are never deleted; they are ended by a
 *  valid_to date so that earlier checks stay traceable. */
export function CapAreas({ areas }: { areas: CapArea[] }) {
  const t = useTranslations("RentLaw");
  const router = useRouter();
  const [f, setF] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF((p) => ({ ...p, [k]: e.target.value }));
  const valid = /^[A-Za-z]{2}$/.test(f.state) && f.municipality.trim().length >= 2 && NUMBER.test(f.cap_percent) && f.valid_from && f.source.trim().length >= 5;
  const send = async (url: string, method: string, body: Record<string, unknown>) => {
    setBusy(true);
    setError(null);
    const res = await bff(url, { method, body: JSON.stringify(body) });
    setBusy(false);
    if (res.ok) {
      setF(EMPTY);
      router.refresh();
    } else setError(res.message);
  };
  const create = () =>
    send("/api/bff/platform/rent-law/cap-areas", "POST", {
      state: f.state.toUpperCase(),
      municipality: f.municipality.trim(),
      municipality_code: f.municipality_code.trim() || null,
      cap_percent: dec(f.cap_percent),
      valid_from: f.valid_from,
      source: f.source.trim(),
    });
  const end = (a: CapArea) => {
    const until = window.prompt(t("endPrompt"), new Date().toISOString().slice(0, 10));
    if (!until) return;
    const { id, ...rest } = a;
    void send(`/api/bff/platform/rent-law/cap-areas/${id}`, "PUT", { ...rest, valid_to: until });
  };
  const input = (k: keyof typeof f, type = "text") => (
    <label className="flex flex-col gap-1">
      <span className={ui.label}>{t(`area.${k}`)}</span>
      <input className={ui.input} type={type} value={f[k]} onChange={set(k)} />
    </label>
  );
  return (
    <div className="flex flex-col gap-3">
      {areas.length ? (
        <div className="overflow-x-auto">
<table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-muted">
              <th>{t("area.state")}</th>
              <th>{t("area.municipality")}</th>
              <th>{t("area.cap_percent")}</th>
              <th>{t("area.period")}</th>
              <th>{t("area.source")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {areas.map((a) => (
              <tr key={a.id} className="border-t">
                <td>{a.state}</td>
                <td>{a.municipality}</td>
                <td className="tabular-nums">{String(Number(a.cap_percent)).replace(".", ",")} %</td>
                <td>
                  {formatDate(a.valid_from)} {a.valid_to ? `bis ${formatDate(a.valid_to)}` : t("area.open")}
                </td>
                <td className="text-xs">{a.source}</td>
                <td>
                  {a.valid_to ? null : (
                    <button type="button" className={ui.button} disabled={busy} onClick={() => end(a)}>
                      {t("area.end")}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
</div>
      ) : (
        <p className="text-sm text-muted">{t("area.none")}</p>
      )}
      <div className="grid gap-2 sm:grid-cols-3">
        {input("state")}
        {input("municipality")}
        {input("municipality_code")}
        {input("cap_percent")}
        {input("valid_from", "date")}
        {input("source")}
      </div>
      <button type="button" className={ui.primary} disabled={busy || !valid} onClick={create}>
        {t("area.add")}
      </button>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
