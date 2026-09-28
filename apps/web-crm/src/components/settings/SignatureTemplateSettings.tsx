"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type SignatureTemplate = { text: string | null; html: string | null; logo_url: string | null };

const PLACEHOLDERS = "{name} {position} {phone} {mobile} {email} {company} {street} {postal_code} {city} {register} {website}";

/** Tenant wide e-mail signature template (operator 27.09.2026): text and HTML building blocks
 *  with placeholders; empty fields fall back to the default rendered from the company data
 *  (`PATCH /tenant/settings`, field `signature_template`). Outgoing mail is plain text with the
 *  text template (review 1.36.0); HTML template and logo only feed the preview. */
export function SignatureTemplateSettings({ initial, canUpdate }: { initial: SignatureTemplate; canUpdate: boolean }) {
  const t = useTranslations("SignatureTemplate");
  const [text, setText] = useState(initial.text ?? "");
  const [html, setHtml] = useState(initial.html ?? "");
  const [logoUrl, setLogoUrl] = useState(initial.logo_url ?? "");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<{ signature_template: SignatureTemplate }>("/api/bff/tenant/settings", {
      method: "PATCH",
      body: JSON.stringify({
        signature_template: { text: text.trim() || null, html: html.trim() || null, logo_url: logoUrl.trim() || null },
      }),
    });
    setBusy(false);
    if (res.ok) setMessage(t("saved"));
    else setError(res.message);
  }

  return (
    <form onSubmit={(e) => void save(e)} className={`${ui.card} flex flex-col gap-3`}>
      <h2 className="text-sm font-semibold">{t("title")}</h2>
      <p className="text-xs text-muted">{t("hint")}</p>
      <p className="text-xs text-muted">
        {t("placeholders")}: <code className={ui.mono}>{PLACEHOLDERS}</code>
      </p>
      <label className="flex flex-col gap-1 text-xs">
        <span className={ui.label}>{t("text")}</span>
        <textarea className={`${ui.input} min-h-32 font-mono`} value={text} disabled={!canUpdate} onChange={(e) => setText(e.target.value)} placeholder={t.raw("textPlaceholder") as string} />
      </label>
      <label className="flex flex-col gap-1 text-xs">
        <span className={ui.label}>{t("html")}</span>
        <textarea className={`${ui.input} min-h-32 font-mono`} value={html} disabled={!canUpdate} onChange={(e) => setHtml(e.target.value)} placeholder={t.raw("htmlPlaceholder") as string} />
      </label>
      <p className="text-xs text-muted" data-testid="signature-template-html-hint">
        {t("htmlHint")}
      </p>
      <label className="flex flex-col gap-1 text-xs sm:max-w-md">
        <span className={ui.label}>{t("logoUrl")}</span>
        <input type="url" className={ui.input} value={logoUrl} disabled={!canUpdate} onChange={(e) => setLogoUrl(e.target.value)} placeholder="https://" />
      </label>
      <p className="text-xs text-muted">{t("logoHint")}</p>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      {message ? <p className="text-xs text-success-fg">{message}</p> : null}
      {canUpdate ? (
        <div>
          <button type="submit" className={ui.primary} disabled={busy}>
            {t("save")}
          </button>
        </div>
      ) : null}
    </form>
  );
}
