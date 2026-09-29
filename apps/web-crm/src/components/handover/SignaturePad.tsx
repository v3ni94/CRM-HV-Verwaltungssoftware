"use client";

import { attachSignatureCanvas, type SignatureController } from "@mhvp/ui/signature-canvas";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import { ROLES, type Item, type Kind, type Signature, mainRoles } from "./types";

export type SignatureCanvasHandle = {
  undo: () => void;
  clear: () => void;
  isEmpty: () => boolean;
  toDataURL: () => string;
};

/** Canvas bound to the shared signature core (packages/ui): normalised strokes, redraw on
 *  resize and rotation, undo. `className` sets the height (h-56 by default). */
export function SignatureCanvas({
  className = "h-56 sm:h-64",
  onReady,
  disabled = false,
  label,
}: {
  className?: string;
  onReady: (handle: SignatureCanvasHandle | null) => void;
  disabled?: boolean;
  label: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const controller = useRef<SignatureController | null>(null);
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const c = attachSignatureCanvas(canvas);
    controller.current = c;
    onReadyRef.current({ undo: c.undo, clear: c.clear, isEmpty: c.isEmpty, toDataURL: c.toDataURL });
    return () => {
      c.destroy();
      controller.current = null;
      onReadyRef.current(null);
    };
  }, []);
  return (
    <canvas
      ref={canvasRef}
      className={`w-full touch-none rounded-md border border-border bg-paper ${className} ${disabled ? "pointer-events-none opacity-60" : ""}`.trim()}
      aria-label={label}
      data-testid="signature-canvas"
    />
  );
}

export function participantName(p: Item): string {
  return [p.first_name, p.last_name].filter(Boolean).join(" ") || String(p.company ?? "");
}

/** Signature form (M30): participant first, then the canvas, then name, role and place. Thin
 *  shell over the shared core; the consent text stays in the parent. */
export function SignaturePad({
  protocolId,
  kind,
  participants,
  signatures,
  disabled,
  onSaved,
}: {
  protocolId: string;
  kind: Kind;
  participants: Item[];
  signatures: Signature[];
  disabled: boolean;
  onSaved: () => void;
}) {
  const t = useTranslations("Handover");
  const [handle, setHandle] = useState<SignatureCanvasHandle | null>(null);
  const [participantId, setParticipantId] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<string>(mainRoles(kind)[1]);
  const [location, setLocation] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const signed = new Set(signatures.filter((s) => !s.invalidated_at).map((s) => s.participant_id).filter(Boolean));

  function pickParticipant(id: string) {
    setParticipantId(id);
    const p = participants.find((x) => x.id === id);
    if (p) {
      setName(participantName(p));
      setRole(String(p.role ?? "other"));
    }
  }

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
        participant_id: participantId || null,
        signed_location: location || null,
      }),
    });
    setBusy(false);
    if (res.ok) {
      handle.clear();
      setParticipantId("");
      setName("");
      setMessage(t("signature.saved"));
      onSaved();
    } else setMessage(res.message);
  }

  return (
    <div className={`${ui.card} flex flex-col gap-3`} data-testid="signature-pad">
      <div>
        <label htmlFor="sig-participant" className={ui.label}>
          {t("signature.participant")}
        </label>
        <select id="sig-participant" className={ui.input} value={participantId} onChange={(e) => pickParticipant(e.target.value)} disabled={disabled}>
          <option value="">{t("signature.free")}</option>
          {participants.map((p) => (
            <option key={p.id} value={p.id} disabled={signed.has(p.id)}>
              {participantName(p)}
              {signed.has(p.id) ? ` (${t("signature.done")})` : ""}
            </option>
          ))}
        </select>
      </div>
      <SignatureCanvas onReady={setHandle} disabled={disabled} label={t("signature.canvas")} />
      <div className="grid gap-3 sm:grid-cols-3">
        <div>
          <label htmlFor="sig-name" className={ui.label}>
            {t("signature.name")}
          </label>
          <input id="sig-name" className={ui.input} value={name} onChange={(e) => setName(e.target.value)} disabled={disabled} autoComplete="off" enterKeyHint="next" />
        </div>
        <div>
          <label htmlFor="sig-role" className={ui.label}>
            {t("signature.role")}
          </label>
          <select id="sig-role" className={ui.input} value={role} onChange={(e) => setRole(e.target.value)} disabled={disabled}>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {t(`roles.${r}`)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="sig-location" className={ui.label}>
            {t("signature.location")}
          </label>
          <input id="sig-location" className={ui.input} value={location} onChange={(e) => setLocation(e.target.value)} disabled={disabled} enterKeyHint="done" />
        </div>
      </div>
      <div className={ui.formActions}>
        <button type="button" className={`${ui.button} ${ui.actionFull}`} onClick={() => handle?.undo()} disabled={disabled || busy}>
          {t("signature.undo")}
        </button>
        <button type="button" className={`${ui.button} ${ui.actionFull}`} onClick={() => handle?.clear()} disabled={disabled || busy}>
          {t("signature.clear")}
        </button>
        <button type="button" className={`${ui.primary} ${ui.actionFull}`} onClick={save} disabled={disabled || busy}>
          {t("signature.save")}
        </button>
      </div>
      {message ? <p className="text-sm text-muted">{message}</p> : null}
    </div>
  );
}
