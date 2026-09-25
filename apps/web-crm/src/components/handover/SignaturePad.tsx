"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import {
  ROLES,
  type Item,
  type Kind,
  type Signature,
  mainRoles,
} from "./types";

/** Canvas signature (finger, pen or mouse) stored as PNG with SHA-256 on the server (M30). */
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
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const dirty = useRef(false);
  const [participantId, setParticipantId] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<string>(mainRoles(kind)[1]);
  const [location, setLocation] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const signed = new Set(
    signatures.map((s) => s.participant_id).filter(Boolean),
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ratio = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.round(rect.width * ratio));
    canvas.height = Math.max(1, Math.round(180 * ratio));
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(ratio, ratio);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, rect.width, 180);
    ctx.lineWidth = 2.2;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = "#1A1A1A";
  }, []);

  function point(e: React.PointerEvent<HTMLCanvasElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  function down(e: React.PointerEvent<HTMLCanvasElement>) {
    if (disabled) return;
    const ctx = e.currentTarget.getContext("2d");
    if (!ctx) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    drawing.current = true;
    const p = point(e);
    ctx.beginPath();
    ctx.moveTo(p.x, p.y);
  }

  function move(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!drawing.current) return;
    const ctx = e.currentTarget.getContext("2d");
    if (!ctx) return;
    const p = point(e);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    dirty.current = true;
  }

  function up() {
    drawing.current = false;
  }

  function clear() {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.restore();
    dirty.current = false;
    setMessage(null);
  }

  function pickParticipant(id: string) {
    setParticipantId(id);
    const p = participants.find((x) => x.id === id);
    if (p) {
      setName(
        [p.first_name, p.last_name].filter(Boolean).join(" ") ||
          String(p.company ?? ""),
      );
      setRole(String(p.role ?? "other"));
    }
  }

  async function save() {
    const canvas = canvasRef.current;
    if (!canvas || !dirty.current) {
      setMessage(t("signature.empty"));
      return;
    }
    setBusy(true);
    setMessage(null);
    const res = await bff<Signature>(
      `/api/bff/handover/protocols/${protocolId}/signatures`,
      {
        method: "POST",
        body: JSON.stringify({
          image: canvas.toDataURL("image/png"),
          signer_name: name || null,
          signer_role: role || null,
          participant_id: participantId || null,
          signed_location: location || null,
        }),
      },
    );
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
    <div
      className={`${ui.card} flex flex-col gap-3`}
      data-testid="signature-pad"
    >
      <div className="grid gap-3 md:grid-cols-4">
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
                {[p.first_name, p.last_name].filter(Boolean).join(" ") ||
                  String(p.company ?? "")}
                {signed.has(p.id) ? ` (${t("signature.done")})` : ""}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="sig-name" className={ui.label}>
            {t("signature.name")}
          </label>
          <input
            id="sig-name"
            className={ui.input}
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={disabled}
          />
        </div>
        <div>
          <label htmlFor="sig-role" className={ui.label}>
            {t("signature.role")}
          </label>
          <select
            id="sig-role"
            className={ui.input}
            value={role}
            onChange={(e) => setRole(e.target.value)}
            disabled={disabled}
          >
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
      <canvas
        ref={canvasRef}
        className="h-[180px] w-full touch-none rounded-md border border-border bg-white"
        aria-label={t("signature.canvas")}
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerLeave={up}
        onPointerCancel={up}
      />
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={ui.button}
          onClick={clear}
          disabled={disabled || busy}
        >
          {t("signature.clear")}
        </button>
        <button
          type="button"
          className={ui.primary}
          onClick={save}
          disabled={disabled || busy}
        >
          {t("signature.save")}
        </button>
        {message ? (
          <span className="self-center text-sm text-muted">{message}</span>
        ) : null}
      </div>
    </div>
  );
}
