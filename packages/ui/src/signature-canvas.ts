/**
 * Headless signature core (M31 WP2, shared by CRM and portal): strokes are stored as
 * normalised point lists (0..1 of the CSS box), so a resize or a rotation of the device
 * redraws them without distortion, and the bitmap follows the CSS box times the device
 * pixel ratio (capped, so the PNG stays under 2 MB). No JSX, no Tailwind. The image is always
 * ink on white paper, never themed (it is a document image). The data URL contract of the
 * API stays `data:image/png;base64,...`.
 */

export type Point = { x: number; y: number };
export type Stroke = Point[];

export type SignatureOptions = {
  paper?: string;
  ink?: string;
  lineWidth?: number;
  /** Upper bound of the device pixel ratio used for the bitmap (default 2). */
  maxRatio?: number;
};

const DEFAULTS: Required<SignatureOptions> = {
  paper: "#ffffff",
  ink: "#1A1A1A",
  lineWidth: 2.2,
  maxRatio: 2,
};

export type SignatureStore = {
  strokes: Stroke[];
  begin: (p: Point) => void;
  extend: (p: Point) => void;
  end: () => void;
  undo: () => Stroke | undefined;
  clear: () => void;
  isEmpty: () => boolean;
  /** Called after every change (stroke added, undo, clear). */
  onChange?: () => void;
};

export function createSignatureStore(): SignatureStore {
  let current: Stroke | null = null;
  const store: SignatureStore = {
    strokes: [],
    begin(p) {
      current = [clamp(p)];
      store.strokes.push(current);
      store.onChange?.();
    },
    extend(p) {
      if (!current) return;
      current.push(clamp(p));
      store.onChange?.();
    },
    end() {
      if (current && current.length === 1) current.push(current[0]!);
      current = null;
      store.onChange?.();
    },
    undo() {
      current = null;
      const removed = store.strokes.pop();
      store.onChange?.();
      return removed;
    },
    clear() {
      current = null;
      store.strokes = [];
      store.onChange?.();
    },
    isEmpty() {
      return store.strokes.length === 0;
    },
  };
  return store;
}

function clamp(p: Point): Point {
  return { x: Math.min(1, Math.max(0, p.x)), y: Math.min(1, Math.max(0, p.y)) };
}

export type SignatureController = {
  store: SignatureStore;
  undo: () => void;
  clear: () => void;
  isEmpty: () => boolean;
  toDataURL: () => string;
  /** Redraw from the strokes (after a resize the bitmap is rebuilt first). */
  redraw: () => void;
  /** Remove listeners and observers. */
  destroy: () => void;
};

/** Attach the store to a canvas: pointer events (with capture, `touch-action: none` is set
 *  on the element), ResizeObserver and orientationchange rebuild the bitmap and redraw. */
export function attachSignatureCanvas(canvas: HTMLCanvasElement, options: SignatureOptions = {}): SignatureController {
  const opts = { ...DEFAULTS, ...options };
  const store = createSignatureStore();
  let drawing = false;
  canvas.style.touchAction = "none";

  const box = () => {
    const rect = canvas.getBoundingClientRect();
    return { width: Math.max(1, rect.width), height: Math.max(1, rect.height), left: rect.left, top: rect.top };
  };

  const ratio = () => {
    const dpr = typeof window !== "undefined" && window.devicePixelRatio ? window.devicePixelRatio : 1;
    return Math.min(opts.maxRatio, Math.max(1, dpr));
  };

  const redraw = () => {
    const { width, height } = box();
    const r = ratio();
    const w = Math.round(width * r);
    const h = Math.round(height * r);
    if (canvas.width !== w) canvas.width = w;
    if (canvas.height !== h) canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = opts.paper;
    ctx.fillRect(0, 0, w, h);
    ctx.lineWidth = opts.lineWidth * r;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = opts.ink;
    for (const stroke of store.strokes) {
      if (stroke.length === 0) continue;
      ctx.beginPath();
      ctx.moveTo(stroke[0]!.x * w, stroke[0]!.y * h);
      for (let i = 1; i < stroke.length; i += 1) ctx.lineTo(stroke[i]!.x * w, stroke[i]!.y * h);
      ctx.stroke();
    }
  };

  const normalise = (e: PointerEvent): Point => {
    const { width, height, left, top } = box();
    return { x: (e.clientX - left) / width, y: (e.clientY - top) / height };
  };

  const down = (e: PointerEvent) => {
    if (e.button !== undefined && e.button !== 0 && e.pointerType === "mouse") return;
    e.preventDefault();
    try {
      canvas.setPointerCapture(e.pointerId);
    } catch {
      /* capture unavailable in some test environments */
    }
    drawing = true;
    store.begin(normalise(e));
    redraw();
  };
  const move = (e: PointerEvent) => {
    if (!drawing) return;
    e.preventDefault();
    store.extend(normalise(e));
    redraw();
  };
  const up = (e: PointerEvent) => {
    if (!drawing) return;
    drawing = false;
    store.end();
    try {
      canvas.releasePointerCapture(e.pointerId);
    } catch {
      /* not captured */
    }
    redraw();
  };

  canvas.addEventListener("pointerdown", down);
  canvas.addEventListener("pointermove", move);
  canvas.addEventListener("pointerup", up);
  canvas.addEventListener("pointercancel", up);
  canvas.addEventListener("pointerleave", up);

  let observer: ResizeObserver | null = null;
  if (typeof ResizeObserver === "function") {
    observer = new ResizeObserver(() => redraw());
    observer.observe(canvas);
  }
  const rotate = () => redraw();
  if (typeof window !== "undefined") window.addEventListener("orientationchange", rotate);

  redraw();
  return {
    store,
    undo() {
      store.undo();
      redraw();
    },
    clear() {
      store.clear();
      redraw();
    },
    isEmpty: () => store.isEmpty(),
    toDataURL: () => canvas.toDataURL("image/png"),
    redraw,
    destroy() {
      canvas.removeEventListener("pointerdown", down);
      canvas.removeEventListener("pointermove", move);
      canvas.removeEventListener("pointerup", up);
      canvas.removeEventListener("pointercancel", up);
      canvas.removeEventListener("pointerleave", up);
      observer?.disconnect();
      if (typeof window !== "undefined") window.removeEventListener("orientationchange", rotate);
    },
  };
}
