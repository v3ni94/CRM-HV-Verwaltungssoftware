import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { SignatureSheet } from "./SignatureSheet";

vi.mock("next/navigation", () => ({
  usePathname: () => "/makler/uebergabe/1",
  useSearchParams: () => new URLSearchParams(),
}));
const controller = { undo: vi.fn(), clear: vi.fn(), isEmpty: vi.fn(() => false), toDataURL: vi.fn(() => "data:image/png;base64,AAAA"), destroy: vi.fn(), redraw: vi.fn(), store: { strokes: [] } };
vi.mock("@mhvp/ui/signature-canvas", () => ({ attachSignatureCanvas: () => controller }));

const participant = { id: "0192abcd-0000-7000-8000-000000000062", role: "moving_in", first_name: "Erika", last_name: "Mieter" };

describe("SignatureSheet", () => {
  afterEach(() => vi.restoreAllMocks());

  it("prefills name and role, shows consent and the hand over hint, closes on success", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: "s1" }, 201));
    const onClose = vi.fn();
    const onSaved = vi.fn();
    renderIntl(<SignatureSheet open onClose={onClose} protocolId="p1" kind="rental" participant={participant} onSaved={onSaved} />);
    expect(screen.getByText("Unterschrift von Erika Mieter")).toBeInTheDocument();
    expect(screen.getByText(/Mit ihrer Unterschrift bestätigen/)).toBeInTheDocument();
    expect(screen.getByText("Bitte das Gerät an Erika Mieter übergeben.")).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toHaveValue("Erika Mieter");
    expect(screen.getByLabelText("Rolle")).toHaveValue("moving_in");
    expect(screen.getByTestId("signature-canvas").className).toContain("h-[45dvh]");
    await userEvent.click(screen.getByText("Unterschrift speichern"));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(onClose).toHaveBeenCalled();
    expect(controller.clear).not.toHaveBeenCalled();
  });

  it("keeps the strokes and shows the message on a 409", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ title: "Konflikt", detail: "Für diese Person liegt bereits eine Unterschrift vor." }, 409));
    const onClose = vi.fn();
    renderIntl(<SignatureSheet open onClose={onClose} protocolId="p1" kind="rental" participant={participant} onSaved={() => undefined} />);
    await userEvent.click(screen.getByText("Unterschrift speichern"));
    expect(await screen.findByRole("alert")).toHaveTextContent("bereits eine Unterschrift");
    expect(onClose).not.toHaveBeenCalled();
    expect(controller.clear).not.toHaveBeenCalled();
  });
});
