import { attachSignatureCanvas, createSignatureStore } from "./signature-canvas";

type Ctx = { calls: string[] } & Record<string, unknown>;

function stubContext(canvas: HTMLCanvasElement): Ctx {
  const ctx: Ctx = { calls: [] };
  for (const name of ["setTransform", "fillRect", "beginPath", "moveTo", "lineTo", "stroke"]) {
    ctx[name] = (...args: unknown[]) => {
      ctx.calls.push(`${name}(${args.map((a) => (typeof a === "number" ? Math.round(a) : String(a))).join(",")})`);
    };
  }
  canvas.getContext = (() => ctx) as unknown as HTMLCanvasElement["getContext"];
  canvas.getBoundingClientRect = () => ({ width: 200, height: 100, left: 10, top: 20, right: 210, bottom: 120, x: 10, y: 20, toJSON: () => ({}) });
  canvas.toDataURL = () => "data:image/png;base64,iVBORw0KGgo=";
  return ctx;
}

function pointer(type: string, x: number, y: number): PointerEvent {
  const event = new MouseEvent(type, { clientX: x, clientY: y, bubbles: true, button: 0 }) as unknown as PointerEvent;
  Object.defineProperty(event, "pointerId", { value: 1 });
  Object.defineProperty(event, "pointerType", { value: "touch" });
  return event;
}

describe("createSignatureStore", () => {
  it("collects normalised strokes, undoes the last one and clears", () => {
    const store = createSignatureStore();
    expect(store.isEmpty()).toBe(true);
    store.begin({ x: 0.1, y: 0.2 });
    store.extend({ x: 0.5, y: 1.4 });
    store.end();
    store.begin({ x: 0.9, y: 0.9 });
    store.end();
    expect(store.strokes).toHaveLength(2);
    expect(store.strokes[0]).toEqual([
      { x: 0.1, y: 0.2 },
      { x: 0.5, y: 1 },
    ]);
    expect(store.strokes[1]).toHaveLength(2);
    store.undo();
    expect(store.strokes).toHaveLength(1);
    store.clear();
    expect(store.isEmpty()).toBe(true);
  });
});

describe("attachSignatureCanvas", () => {
  let observed: (() => void) | null = null;
  beforeEach(() => {
    observed = null;
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(cb: () => void) {
          observed = cb;
        }
        observe() {}
        disconnect() {}
      },
    );
    Object.defineProperty(window, "devicePixelRatio", { value: 3, configurable: true });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("turns pointer down, move and up into one normalised stroke and caps the bitmap ratio", () => {
    const canvas = document.createElement("canvas");
    const ctx = stubContext(canvas);
    const sig = attachSignatureCanvas(canvas);
    expect(canvas.style.touchAction).toBe("none");
    expect(canvas.width).toBe(400);
    expect(canvas.height).toBe(200);
    canvas.dispatchEvent(pointer("pointerdown", 10, 20));
    canvas.dispatchEvent(pointer("pointermove", 110, 70));
    canvas.dispatchEvent(pointer("pointerup", 110, 70));
    expect(sig.store.strokes).toEqual([
      [
        { x: 0, y: 0 },
        { x: 0.5, y: 0.5 },
      ],
    ]);
    expect(sig.isEmpty()).toBe(false);
    expect(ctx.calls).toContain("lineTo(200,100)");
    expect(sig.toDataURL()).toMatch(/^data:image\/png;base64,/);
    sig.destroy();
  });

  it("redraws every stroke on resize, undoes the last stroke and clears", () => {
    const canvas = document.createElement("canvas");
    const ctx = stubContext(canvas);
    const sig = attachSignatureCanvas(canvas);
    for (const x of [10, 60]) {
      canvas.dispatchEvent(pointer("pointerdown", x, 20));
      canvas.dispatchEvent(pointer("pointermove", x + 20, 40));
      canvas.dispatchEvent(pointer("pointerup", x + 20, 40));
    }
    ctx.calls.length = 0;
    canvas.getBoundingClientRect = () => ({ width: 400, height: 100, left: 0, top: 0, right: 400, bottom: 100, x: 0, y: 0, toJSON: () => ({}) });
    observed?.();
    expect(canvas.width).toBe(800);
    expect(ctx.calls.filter((c) => c.startsWith("beginPath"))).toHaveLength(2);
    expect(ctx.calls).toContain("moveTo(200,0)");
    sig.undo();
    expect(sig.store.strokes).toHaveLength(1);
    sig.clear();
    expect(sig.isEmpty()).toBe(true);
    sig.destroy();
  });
});
