import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { SignaturePad } from "./SignaturePad";

const controller = { undo: vi.fn(), clear: vi.fn(), isEmpty: vi.fn(() => true), toDataURL: vi.fn(() => "data:image/png;base64,AAAA"), destroy: vi.fn(), redraw: vi.fn(), store: { strokes: [] } };
vi.mock("@mhvp/ui/signature-canvas", () => ({ attachSignatureCanvas: () => controller }));

const participants = [{ id: "0192abcd-0000-7000-8000-000000000062", role: "moving_in", first_name: "Erika", last_name: "Mieter" }];

describe("SignaturePad", () => {
  afterEach(() => vi.restoreAllMocks());

  it("puts the participant before the canvas, uses a 56 px high touch-none canvas and refuses an empty signature", async () => {
    renderIntl(<SignaturePad protocolId="p1" kind="rental" participants={participants} signatures={[]} disabled={false} onSaved={() => undefined} />);
    const select = screen.getByLabelText("Beteiligter");
    const canvas = screen.getByTestId("signature-canvas");
    expect(select.compareDocumentPosition(canvas) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(canvas.className).toContain("h-56");
    expect(canvas.className).toContain("touch-none");
    await userEvent.click(screen.getByText("Unterschrift speichern"));
    expect(screen.getByText("Bitte zuerst unterschreiben.")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Rückgängig"));
    expect(controller.undo).toHaveBeenCalled();
  });

  it("posts the image with the participant id and prefilled name", async () => {
    controller.isEmpty.mockReturnValue(false);
    const bodies: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      if (typeof init?.body === "string") bodies.push(init.body);
      return jsonResponse({ id: "s1" }, 201);
    });
    const onSaved = vi.fn();
    renderIntl(<SignaturePad protocolId="p1" kind="rental" participants={participants} signatures={[]} disabled={false} onSaved={onSaved} />);
    await userEvent.selectOptions(screen.getByLabelText("Beteiligter"), participants[0]!.id);
    expect(screen.getByLabelText("Name")).toHaveValue("Erika Mieter");
    await userEvent.click(screen.getByText("Unterschrift speichern"));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(JSON.parse(bodies[0]!)).toMatchObject({ image: "data:image/png;base64,AAAA", participant_id: participants[0]!.id, signer_name: "Erika Mieter", signer_role: "moving_in" });
    expect(screen.getByText("Unterschrift gespeichert.")).toBeInTheDocument();
  });
});
