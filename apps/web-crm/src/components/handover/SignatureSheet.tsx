"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { Sheet } from "@/components/ui/Sheet";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import { SignatureCanvas, participantName, type SignatureCanvasHandle } from "./SignaturePad";
import { ROLES, type Item, type Kind, type Signature, mainRoles } from "./types";

export type SignatureSheetProps = {
  open: boolean;
  onClose: () => void;
  protocolId: string;
  kind: Kind;
  /** Participant to sign for; null for an additional person (free entry). */
  participant: Item | null;
  onSaved: () => Promise<void> | void;
};

/** Full screen signature per participant (M31 WP2): consent text, prefilled name and role
 *  (editable), place, the hint to hand over the device, a tall canvas and the footer with
 *  undo, clear and save. On success the sheet closes; on an error (409 included) the strokes
 *  stay and the message is shown. */
export function SignatureSheet({ open, onClose, protocolId, kind, participant, onSaved }: SignatureSheetProps) {
  const t = useTranslations("Handover");
  const [handle, setHandle] = useState<SignatureCanvasHandle | null>(null);
  const [name, setName] = useState("");
  const [role, setRole] = useState<string>(mainRoles(kind)[1]);
  const [location, setLocation] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => {
    if (!open) return;
    setName(participant ? participantName(participant) : "");
    setRole(participant ? String(participant.role ?? "other") : mainRoles(kind)[1]);
    setLocation("");
    setMessage(null);
  }, [open, participant, kind]);

  async function save() {
    if (!handle || handle.isEmpty()) {
      setMessage(t("signature.empty"));
      return;
    }
    setBusy(true);
    setMessage(null);
    const res = await bff<Signature>(`/api/bff/handover/protocols/${protocolId}/signatures`, {
      method: "POST",
      body: JSON.stringify({
        image: handle.toDataURL(),
        signer_name: name || null,
        signer_role: role || null,
        participant_id: participant?.id ?? null,
        signed_location: location || null,
      }),
    });
    setBusy(false);
    if (res.ok) {
      await onSaved();
      onClose();
    } else setMessage(res.message);
  }

  const title = participant ? t("signature.of", { name: participantName(participant) || t("signature.noName") }) : t("signature.sheetTitle");
  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={title}
      size="full"
      testId="signature-sheet"
      footer={
        <div className={ui.formActions}>
          <button type="button" className={`${ui.button} ${ui.actionFull}`} onClick={() => handle?.undo()} disabled={busy}>
            {t("signature.undo")}
          </button>
          <button type="button" className={`${ui.button} ${ui.actionFull}`} onClick={() => handle?.clear()} disabled={busy}>
            {t("signature.clear")}
          </button>
          <button type="button" className={`${ui.primary} ${ui.actionFull}`} onClick={save} disabled={busy}>
            {t("signature.save")}
          </button>
        </div>
      }
    >
      <div className="flex flex-col gap-3">
        <p className={ui.notice}>{t("signature.consent")}</p>
        {name ? <p className="text-sm font-medium">{t("signature.handDevice", { name })}</p> : null}
        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <label htmlFor="sheet-sig-name" className={ui.label}>
              {t("signature.name")}
            </label>
            <input id="sheet-sig-name" className={ui.input} value={name} onChange={(e) => setName(e.target.value)} autoComplete="off" enterKeyHint="next" />
          </div>
          <div>
            <label htmlFor="sheet-sig-role" className={ui.label}>
              {t("signature.role")}
            </label>
            <select id="sheet-sig-role" className={ui.input} value={role} onChange={(e) => setRole(e.target.value)}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {t(`roles.${r}`)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="sheet-sig-location" className={ui.label}>
              {t("signature.location")}
            </label>
            <input id="sheet-sig-location" className={ui.input} value={location} onChange={(e) => setLocation(e.target.value)} enterKeyHint="done" />
          </div>
        </div>
        <SignatureCanvas className="h-[45dvh] min-h-56 landscape:h-[60dvh]" onReady={setHandle} label={t("signature.canvas")} />
        {message ? (
          <p role="alert" className={ui.alert}>
            {message}
          </p>
        ) : null}
      </div>
    </Sheet>
  );
}
