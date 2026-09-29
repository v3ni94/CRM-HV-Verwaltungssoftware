"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import { ROLES, type Item, type Kind, type Signature, mainRoles } from "./types";

/** One stroke in normalised canvas coordinates (0 to 1 of the drawing width and height), so a
 *  rotation of the device or a wider canvas redraws the same signature without loss (M31 WP5).
 *  Integrator note: WP2 delivers packages/ui/src/signature-canvas.ts with the same model; this
 *  portal core is to be replaced by that shared module once both packages are merged. */
export type Point = { x: number; y: number };
export type Stroke = Point[];

// Pen on paper in both modes: white ground and dark ink (same values as the --mhvp-color-paper
// and --mhvp-color-ink tokens), never themed.
const PAPER = "#ffffff";
const INK = "#1A1A1A";
const LINE_WIDTH = 2.2;

export function normalise(point: Point, rect: { width: number; height: number }): Point {
  return {
    x: rect.width > 0 ? Math.min(1, Math.max(0, point.x / rect.width)) : 0,
    y: rect.height > 0 ? Math.min(1, Math.max(0, point.y / rect.height)) : 0,
  };
}

/** Redraws all strokes at the current canvas size (device pixel ratio aware). */
export function drawStrokes(canvas: HTMLCanvasElement, strokes: Stroke[]): void {
  const ratio = typeof window === "undefined" ? 1 : window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.fillStyle = PAPER;
  ctx.fillRect(0, 0, width, height);
  ctx.lineWidth = LINE_WIDTH;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.strokeStyle = INK;
  for (const stroke of strokes) {
    if (stroke.length === 0) continue;
    ctx.beginPath();
    const first = stroke[0]!;
    ctx.moveTo(first.x * width, first.y * height);
    if (stroke.length === 1) ctx.lineTo(first.x * width + 0.1, first.y * height);
    for (const p of stroke.slice(1)) ctx.lineTo(p.x * width, p.y * height);
    ctx.stroke();
  }
}

/** Canvas signature (finger, pen or mouse) stored as PNG with SHA-256 on the server (M30):
 *  strokes are kept normalised, Rückgängig removes the last stroke, Leeren removes all. */
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
  const strokesRef = useRef<Stroke[]>([]);
  const current = useRef<Stroke | null>(null);
  const [strokeCount, setStrokeCount] = useState(0);
  const [participantId, setParticipantId] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<string>(mainRoles(kind)[1]);
  const [location, setLocation] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const signed = new Set(signatures.map((s) => s.participant_id).filter(Boolean));

  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    if (canvas) drawStrokes(canvas, strokesRef.current);
  }, []);

  useEffect(() => {
    redraw();
    const canvas = canvasRef.current;
    if (!canvas || typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", redraw);
      return () => window.removeEventListener("resize", redraw);
    }
    const observer = new ResizeObserver(() => redraw());
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [redraw]);

  function point(e: React.PointerEvent<HTMLCanvasElement>): Point {
    const rect = e.currentTarget.getBoundingClientRect();
    return normalise({ x: e.clientX - rect.left, y: e.clientY - rect.top }, rect);
  }

  function down(e: React.PointerEvent<HTMLCanvasElement>) {
    if (disabled) return;
    e.currentTarget.setPointerCapture?.(e.pointerId);
    current.current = [point(e)];
  }

  function move(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!current.current) return;
    current.current.push(point(e));
    const canvas = canvasRef.current;
    if (canvas) drawStrokes(canvas, [...strokesRef.current, current.current]);
  }

  function up() {
    if (!current.current) return;
    strokesRef.current = [...strokesRef.current, current.current];
    current.current = null;
    setStrokeCount(strokesRef.current.length);
    redraw();
  }

  function undo() {
    strokesRef.current = strokesRef.current.slice(0, -1);
    setStrokeCount(strokesRef.current.length);
    setMessage(null);
    redraw();
  }

  function clear() {
    strokesRef.current = [];
    setStrokeCount(0);
    setMessage(null);
    redraw();
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
    const canvas = canvasRef.current;
    if (!canvas || strokesRef.current.length === 0) {
      setMessage(t("signature.empty"));
      return;
    }
    setBusy(true);
    setMessage(null);
    const res = await bff<Signature>(`${base}/signatures`, {
      method: "POST",
      body: JSON.stringify({
        image: canvas.toDataURL("image/png"),
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
        className="h-56 w-full touch-none rounded-md border border-field-line bg-paper sm:h-64"
        aria-label={t("signature.canvas")}
        data-strokes={strokeCount}
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerLeave={up}
        onPointerCancel={up}
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
