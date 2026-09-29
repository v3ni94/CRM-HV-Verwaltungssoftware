"use client";

import { attachSignatureCanvas, type SignatureController } from "@mhvp/ui/signature-canvas";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import { ROLES, type Item, type Kind, type Signature, mainRoles } from "./types";

/** Canvas signature (finger, pen or mouse) stored as PNG with SHA-256 on the server (M30).
 *  The drawing core is the shared headless module of packages/ui (M31 WP2): strokes are kept
 *  normalised (0 to 1 of the drawing box), so a rotation of the device or a wider canvas
 *  redraws the same signature without loss; Rückgängig removes the last stroke, Leeren all. */
export function SignaturePad({
  base,
  kind,
  participants,
  signatures,
  disabled,
  onSaved,
}: {
  /** BFF path of the protocol, e.g. /api/bff/portal/handover/<id>. */
  base: string;
  kind: Kind;
  participants: Item[];
  signatures: Signature[];
  disabled: boolean;
  onSaved: () => void;
}) {
  const t = useTranslations("Handover");
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const controller = useRef<SignatureController | null>(null);
  const [strokeCount, setStrokeCount] = useState(0);
  const [participantId, setParticipantId] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<string>(mainRoles(kind)[1]);
  const [location, setLocation] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const signed = new Set(signatures.map((s) => s.participant_id).filter(Boolean));

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const c = attachSignatureCanvas(canvas);
    c.store.onChange = () => setStrokeCount(c.store.strokes.length);
    controller.current = c;
    return () => {
      c.destroy();
      controller.current = null;
    };
  }, []);

  function undo() {
    controller.current?.undo();
    setMessage(null);
  }

  function clear() {
    controller.current?.clear();
    setMessage(null);
  }

  function pickParticipant(id: string) {
    setParticipantId(id);
    const p = participants.find((x) => x.id === id);
    if (p) {
      setName([p.first_name, p.last_name].filter(Boolean).join(" ") || String(p.company ?? ""));
      setRole(String(p.role ?? "other"));
    }
  }

  async function save() {
    const c = controller.current;
    if (!c || c.isEmpty()) {
      setMessage(t("signature.empty"));
      return;
    }
    setBusy(true);
    setMessage(null);
    const res = await bff<Signature>(`${base}/signatures`, {
      method: "POST",
      body: JSON.stringify({
        image: c.toDataURL(),
        signer_name: name || null,
        signer_role: role || null,
        participant_id: participantId || null,
        signed_location: location || null,
      }),
    });
    setBusy(false);
    if (res.ok) {
      clear();
      setParticipantId("");
      setName("");
      setMessage(t("signature.saved"));
      onSaved();
    } else {
      setMessage(res.message);
    }
  }

  return (
    <div className={`${ui.card} flex flex-col gap-3`} data-testid="signature-pad">
      <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-4">
        <div>
          <label htmlFor="sig-participant" className={ui.label}>
            {t("signature.participant")}
          </label>
          <select
            id="sig-participant"
            className={ui.input}
            value={participantId}
            onChange={(e) => pickParticipant(e.target.value)}
            disabled={disabled}
          >
            <option value="">{t("signature.free")}</option>
            {participants.map((p) => (
              <option key={p.id} value={p.id} disabled={signed.has(p.id)}>
                {[p.first_name, p.last_name].filter(Boolean).join(" ") || String(p.company ?? "")}
                {signed.has(p.id) ? ` (${t("signature.done")})` : ""}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="sig-name" className={ui.label}>
            {t("signature.name")}
          </label>
          <input id="sig-name" className={ui.input} value={name} onChange={(e) => setName(e.target.value)} disabled={disabled} />
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
          <input
            id="sig-location"
            className={ui.input}
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            disabled={disabled}
          />
        </div>
      </div>
      <p className="text-xs text-muted">{t("signature.device")}</p>
      <canvas
        ref={canvasRef}
        className={`h-56 w-full touch-none rounded-md border border-field-line bg-paper sm:h-64 ${disabled ? "pointer-events-none opacity-60" : ""}`.trim()}
        aria-label={t("signature.canvas")}
        data-strokes={strokeCount}
      />
      <div className="flex flex-wrap gap-2">
        <button type="button" className={ui.button} onClick={undo} disabled={disabled || busy || strokeCount === 0}>
          {t("signature.undo")}
        </button>
        <button type="button" className={ui.button} onClick={clear} disabled={disabled || busy}>
          {t("signature.clear")}
        </button>
        <button type="button" className={ui.primary} onClick={save} disabled={disabled || busy}>
          {t("signature.save")}
        </button>
        {message ? <span className="self-center text-sm text-muted">{message}</span> : null}
      </div>
    </div>
  );
}
