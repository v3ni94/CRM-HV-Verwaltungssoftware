"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type SignatureProfileData = {
  membership_id: string;
  position: string | null;
  phone: string | null;
  mobile_phone: string | null;
  catalogue: string[];
};

export type SignaturePreviewData = { membership_id: string; text: string; html: string };

const CUSTOM = "__custom__";

/** Position picker (operator 27.09.2026): the catalogue positions as a dropdown plus a free
 *  text entry; a free text position is remembered per tenant by the server and appears in the
 *  dropdown afterwards. */
export function PositionPicker({
  value,
  catalogue,
  onChange,
  idPrefix,
}: {
  value: string;
  catalogue: string[];
  onChange: (next: string) => void;
  idPrefix: string;
}) {
  const t = useTranslations("Signature");
  const inCatalogue = value === "" || catalogue.includes(value);
  const [custom, setCustom] = useState(!inCatalogue);
  return (
    <div className="flex flex-col gap-1.5">
      <label className="flex flex-col gap-1 text-xs">
        <span className={ui.label}>{t("position")}</span>
        <select
          id={`${idPrefix}-position`}
          className={ui.input}
          value={custom ? CUSTOM : value}
          onChange={(e) => {
            if (e.target.value === CUSTOM) {
              setCustom(true);
              onChange("");
            } else {
              setCustom(false);
              onChange(e.target.value);
            }
          }}
        >
          <option value="">{t("noPosition")}</option>
          {catalogue.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
          <option value={CUSTOM}>{t("customPosition")}</option>
        </select>
      </label>
      {custom ? (
        <label className="flex flex-col gap-1 text-xs">
          <span className={ui.label}>{t("customPositionLabel")}</span>
          <input
            id={`${idPrefix}-position-custom`}
            className={ui.input}
            maxLength={120}
            value={value}
            placeholder={t("customPositionPlaceholder")}
            onChange={(e) => onChange(e.target.value)}
          />
        </label>
      ) : null}
    </div>
  );
}

/** Own position, extension number and signature preview in Einstellungen, Profil. The
 *  signature itself is rendered by the server (`GET /mail/signature/preview`) from the
 *  tenant template, so the preview here is exactly what outgoing mail carries. */
export function SignatureProfile({
  initialProfile,
  initialPreview,
}: {
  initialProfile: SignatureProfileData | null;
  initialPreview: SignaturePreviewData | null;
}) {
  const t = useTranslations("Signature");
  const [position, setPosition] = useState(initialProfile?.position ?? "");
  const [phone, setPhone] = useState(initialProfile?.phone ?? "");
  const [catalogue, setCatalogue] = useState(initialProfile?.catalogue ?? []);
  const [preview, setPreview] = useState(initialPreview);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!initialProfile) return null;

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<SignatureProfileData>("/api/bff/mail/signature/profile", {
      method: "PUT",
      body: JSON.stringify({ position: position.trim() || null, phone: phone.trim() || null }),
    });
    if (!res.ok) {
      setBusy(false);
      setError(res.message);
      return;
    }
    setCatalogue(res.data.catalogue);
    setPosition(res.data.position ?? "");
    const fresh = await bff<SignaturePreviewData>("/api/bff/mail/signature/preview");
    setBusy(false);
    if (fresh.ok) setPreview(fresh.data);
    setMessage(t("saved"));
  }

  return (
    <section className={ui.card}>
      <h2 className="text-sm font-semibold">{t("title")}</h2>
      <p className="mt-1 text-xs text-muted">{t("hint")}</p>
      <form onSubmit={(e) => void save(e)} className="mt-3 grid gap-3 sm:grid-cols-2">
        <PositionPicker value={position} catalogue={catalogue} onChange={setPosition} idPrefix="profile" />
        <label className="flex flex-col gap-1 text-xs">
          <span className={ui.label}>{t("phone")}</span>
          <input
            type="tel"
            className={ui.input}
            maxLength={40}
            value={phone}
            placeholder="02173 12345"
            onChange={(e) => setPhone(e.target.value)}
          />
        </label>
        <p className="text-xs text-muted sm:col-span-2">{t("phoneHint")}</p>
        {error ? (
          <p role="alert" className={`${ui.alert} sm:col-span-2`}>
            {error}
          </p>
        ) : null}
        {message ? <p className="text-xs text-success-fg sm:col-span-2">{message}</p> : null}
        <div className="sm:col-span-2">
          <button type="submit" className={ui.primary} disabled={busy}>
            {t("save")}
          </button>
        </div>
      </form>
      {preview ? (
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <div>
            <h3 className={ui.label}>{t("previewText")}</h3>
            <pre className="mt-1 whitespace-pre-wrap rounded-md border border-border bg-surface p-3 text-xs" data-testid="signature-text">
              {preview.text}
            </pre>
          </div>
          <div>
            <h3 className={ui.label}>{t("previewHtml")}</h3>
            <iframe
              title={t("previewHtml")}
              sandbox=""
              className="mt-1 h-56 w-full rounded-md border border-border bg-white"
              srcDoc={`<!doctype html><html><body style="margin:12px;background:#fff;">${preview.html}</body></html>`}
            />
          </div>
        </div>
      ) : null}
    </section>
  );
}

/** Admin editor for another member's position and extension (Einstellungen, Benutzer). */
export function MemberPositionEditor({
  membershipId,
  position,
  phone,
  catalogue,
  onSaved,
}: {
  membershipId: string;
  position: string | null | undefined;
  phone: string | null | undefined;
  catalogue: string[];
  onSaved: (patch: { position: string | null; phone: string | null }) => void;
}) {
  const t = useTranslations("Signature");
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(position ?? "");
  const [phoneValue, setPhoneValue] = useState(phone ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    const patch = { position: value.trim() || null, phone: phoneValue.trim() || null };
    const res = await bff<null>(`/api/bff/tenant/members/${membershipId}/position`, {
      method: "PUT",
      body: JSON.stringify(patch),
    });
    setBusy(false);
    if (res.ok) {
      onSaved(patch);
      setOpen(false);
    } else {
      setError(res.message);
    }
  }

  if (!open) {
    return (
      <button type="button" className={ui.buttonSm} onClick={() => setOpen(true)}>
        {position ? t("positionShow", { position }) : t("editPosition")}
      </button>
    );
  }
  return (
    <div className="flex flex-col gap-1.5 rounded-md border border-border bg-surface p-2">
      <PositionPicker value={value} catalogue={catalogue} onChange={setValue} idPrefix={`member-${membershipId}`} />
      <label className="flex flex-col gap-1 text-xs">
        <span className={ui.label}>{t("phone")}</span>
        <input type="tel" className={ui.input} maxLength={40} value={phoneValue} onChange={(e) => setPhoneValue(e.target.value)} />
      </label>
      {error ? <p className={ui.error}>{error}</p> : null}
      <div className="flex gap-2">
        <button type="button" className={ui.button} disabled={busy} onClick={() => void save()}>
          {t("save")}
        </button>
        <button type="button" className={ui.button} disabled={busy} onClick={() => setOpen(false)}>
          {t("cancel")}
        </button>
      </div>
    </div>
  );
}
