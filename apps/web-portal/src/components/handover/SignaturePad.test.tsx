import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { SignaturePad, drawStrokes, normalise } from "./SignaturePad";

/** jsdom has no canvas: a minimal 2D context records the calls we assert on. */
function stubCanvas() {
  const calls: string[] = [];
  const ctx = {
    setTransform: vi.fn(),
    fillRect: vi.fn(() => calls.push("fillRect")),
    beginPath: vi.fn(() => calls.push("beginPath")),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(() => calls.push("stroke")),
    fillStyle: "",
    strokeStyle: "",
    lineWidth: 0,
    lineCap: "",
    lineJoin: "",
  };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(() => ctx as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockReturnValue("data:image/png;base64,QUJD");
  vi.spyOn(HTMLCanvasElement.prototype, "getBoundingClientRect").mockReturnValue({
    x: 0,
    y: 0,
    top: 0,
    left: 0,
    right: 300,
    bottom: 200,
    width: 300,
    height: 200,
    toJSON: () => ({}),
  } as DOMRect);
  return { ctx, calls };
}

function draw(canvas: HTMLCanvasElement, from: [number, number], to: [number, number]) {
  fireEvent.pointerDown(canvas, { clientX: from[0], clientY: from[1], pointerId: 1 });
  fireEvent.pointerMove(canvas, { clientX: to[0], clientY: to[1], pointerId: 1 });
  fireEvent.pointerUp(canvas, { pointerId: 1 });
}

describe("SignaturePad", () => {
  afterEach(() => vi.restoreAllMocks());

  it("keeps strokes normalised and redraws them at a new size (rotation)", () => {
    expect(normalise({ x: 150, y: 50 }, { width: 300, height: 200 })).toEqual({ x: 0.5, y: 0.25 });
    expect(normalise({ x: -5, y: 500 }, { width: 300, height: 200 })).toEqual({ x: 0, y: 1 });
    const { ctx } = stubCanvas();
    const canvas = document.createElement("canvas");
    drawStrokes(canvas, [[{ x: 0.5, y: 0.25 }, { x: 1, y: 1 }]]);
    expect(ctx.moveTo).toHaveBeenCalledWith(150, 50);
    expect(ctx.lineTo).toHaveBeenCalledWith(300, 200);
    expect(ctx.stroke).toHaveBeenCalledTimes(1);
  });

  it("offers Rückgängig for the last stroke and Leeren for all, and refuses to save an empty pad", async () => {
    stubCanvas();
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}, 200));
    renderIntl(<SignaturePad base="/api/bff/portal/handover/x" kind="rental" participants={[]} signatures={[]} disabled={false} onSaved={vi.fn()} />);
    const canvas = screen.getByLabelText("Unterschriftsfeld") as HTMLCanvasElement;
    expect(canvas.className).toContain("h-56");
    expect(canvas.className).toContain("sm:h-64");
    const undo = screen.getByRole("button", { name: "Rückgängig" });
    expect(undo).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Unterschrift speichern" }));
    expect(screen.getByText("Bitte zuerst unterschreiben.")).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
    draw(canvas, [10, 10], [50, 60]);
    draw(canvas, [60, 10], [90, 60]);
    expect(canvas).toHaveAttribute("data-strokes", "2");
    await userEvent.click(undo);
    expect(canvas).toHaveAttribute("data-strokes", "1");
    await userEvent.click(screen.getByRole("button", { name: "Leeren" }));
    expect(canvas).toHaveAttribute("data-strokes", "0");
    expect(undo).toBeDisabled();
  });

  it("posts the PNG with signer name, role and participant", async () => {
    stubCanvas();
    const calls: { url: string; body: string }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      calls.push({ url: String(input), body: String(init?.body ?? "") });
      return jsonResponse({ id: "s1" }, 201);
    });
    const onSaved = vi.fn();
    renderIntl(
      <SignaturePad
        base="/api/bff/portal/handover/x"
        kind="rental"
        participants={[{ id: "p1", first_name: "Erika", last_name: "Muster", role: "moving_in" }]}
        signatures={[]}
        disabled={false}
        onSaved={onSaved}
      />,
    );
    await userEvent.selectOptions(screen.getByLabelText("Beteiligter"), "p1");
    expect(screen.getByLabelText("Name")).toHaveValue("Erika Muster");
    draw(screen.getByLabelText("Unterschriftsfeld") as HTMLCanvasElement, [10, 10], [50, 60]);
    await userEvent.click(screen.getByRole("button", { name: "Unterschrift speichern" }));
    expect(calls[0]?.url).toBe("/api/bff/portal/handover/x/signatures");
    expect(JSON.parse(calls[0]?.body ?? "{}")).toMatchObject({
      image: "data:image/png;base64,QUJD",
      signer_name: "Erika Muster",
      signer_role: "moving_in",
      participant_id: "p1",
    });
    expect(onSaved).toHaveBeenCalled();
    expect(screen.getByText("Unterschrift gespeichert.")).toBeInTheDocument();
  });
});
