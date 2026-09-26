"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Erledigungsarten je Mandant (Regel M19-07, Entscheidung M19-04 vom 26.09.2026): eingebaute
 *  Arten lassen sich abschalten (außer Sonstiges und Zusammengeführt), bis zu 30 eigene Arten
 *  (Code als Slug plus Bezeichnung) kommen hinzu. Gespeichert über `PATCH /tenant/settings`
 *  (`resolution_kinds`), gelesen über `GET /tickets/resolution-kinds`. Jede Änderung wird als
 *  `tenant_settings.updated` protokolliert. */
export type ResolutionKindsConfig = { disabled: string[]; custom: { code: string; label: string }[] };
type KindRow = { code: string; label: string; builtin: boolean; active: boolean };

export const PROTECTED_KINDS = ["sonstiges", "zusammengefuehrt"] as const;
export const MAX_CUSTOM_KINDS = 30;
const CODE_PATTERN = /^[a-z0-9][a-z0-9_]{1,31}$/;

export function ResolutionKindsSettings({ initial, canUpdate }: { initial: ResolutionKindsConfig; canUpdate: boolean }) {
  const t = useTranslations("ResolutionKindsSettings");
  const [config, setConfig] = useState<ResolutionKindsConfig>(initial);
  const [builtins, setBuiltins] = useState<KindRow[] | null>(null);
  const [code, setCode] = useState("");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void bff<{ kinds: KindRow[] }>("/api/bff/tickets/resolution-kinds").then((res) => {
      if (cancelled) return;
      if (res.ok) setBuiltins(res.data.kinds.filter((k) => k.builtin));
      else setError(res.message);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  async function save(next: ResolutionKindsConfig) {
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<{ resolution_kinds: ResolutionKindsConfig }>("/api/bff/tenant/settings", {
      method: "PATCH",
      body: JSON.stringify({ resolution_kinds: next }),
    });
    setBusy(false);
    if (res.ok) {
      setConfig(res.data.resolution_kinds);
      setMessage(t("saved"));
      return true;
    }
    setError(res.message);
    return false;
  }

  function toggleBuiltin(kind: string, active: boolean) {
    const disabled = active ? config.disabled.filter((c) => c !== kind) : [...config.disabled, kind];
    void save({ ...config, disabled });
  }

  async function addCustom() {
    const nextCode = code.trim();
    const nextLabel = label.trim();
    if (!CODE_PATTERN.test(nextCode)) {
      setError(t("codeInvalid"));
      return;
    }
    if (builtins?.some((k) => k.code === nextCode) || config.custom.some((k) => k.code === nextCode)) {
      setError(t("codeTaken"));
      return;
    }
    if (!nextLabel) {
      setError(t("labelRequired"));
      return;
    }
    if (config.custom.length >= MAX_CUSTOM_KINDS) {
      setError(t("limit", { max: MAX_CUSTOM_KINDS }));
      return;
    }
    if (await save({ ...config, custom: [...config.custom, { code: nextCode, label: nextLabel }] })) {
      setCode("");
      setLabel("");
    }
  }

  function removeCustom(kind: string) {
    void save({ ...config, custom: config.custom.filter((k) => k.code !== kind) });
  }

  const readOnly = !canUpdate || busy;
  return (
    <section className={ui.card} aria-labelledby="resolution-kinds-title" data-testid="resolution-kinds">
      <div className="flex flex-col gap-3">
        <h2 id="resolution-kinds-title" className={ui.h2}>
          {t("title")}
        </h2>
        <p className={ui.help}>{t("description")}</p>
        <h3 className="text-sm font-semibold">{t("builtinTitle")}</h3>
        {builtins === null ? (
          <p className={ui.help}>{t("loading")}</p>
        ) : (
          <ul className="grid gap-1 sm:grid-cols-2">
            {builtins.map((k) => {
              const isProtected = (PROTECTED_KINDS as readonly string[]).includes(k.code);
              const active = !config.disabled.includes(k.code);
              return (
                <li key={k.code}>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={active}
                      disabled={readOnly || isProtected}
                      aria-label={k.label}
                      onChange={(e) => toggleBuiltin(k.code, e.target.checked)}
                    />
                    <span>{k.label}</span>
                    {isProtected ? <span className="text-xs text-muted">{t("protected")}</span> : null}
                  </label>
                </li>
              );
            })}
          </ul>
        )}
        <h3 className="text-sm font-semibold">{t("customTitle", { count: config.custom.length, max: MAX_CUSTOM_KINDS })}</h3>
        {config.custom.length === 0 ? (
          <p className={ui.help}>{t("customEmpty")}</p>
        ) : (
          <ul className="flex flex-col gap-1" data-testid="resolution-kinds-custom">
            {config.custom.map((k) => (
              <li key={k.code} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                <span>
                  {k.label} <span className="text-xs text-muted">({k.code})</span>
                </span>
                {canUpdate ? (
                  <button type="button" className={ui.secondary} disabled={busy} onClick={() => removeCustom(k.code)}>
                    {t("remove")}
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
        {canUpdate ? (
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("code")}</span>
              <input className={ui.input} value={code} maxLength={32} disabled={busy} onChange={(e) => setCode(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("label")}</span>
              <input className={ui.input} value={label} maxLength={60} disabled={busy} onChange={(e) => setLabel(e.target.value)} />
            </label>
            <button type="button" className={ui.primary} disabled={busy || code.trim() === "" || label.trim() === ""} onClick={() => void addCustom()}>
              {t("add")}
            </button>
          </div>
        ) : (
          <p className={ui.help}>{t("readOnly")}</p>
        )}
        <p className={ui.help}>{t("codeHint")}</p>
        {message ? <span className="text-xs text-success-fg">{message}</span> : null}
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
      </div>
    </section>
  );
}
