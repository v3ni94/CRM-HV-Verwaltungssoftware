import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ImportUndoDialog } from "./ImportUndoDialog";

vi.mock("next/navigation", () => ({
  usePathname: () => "/imports",
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }),
}));

describe("ImportUndoDialog (GAH-407)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads nothing while closed", () => {
    renderIntl(<ImportUndoDialog importId="i1" open={false} onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the dry run with kept records and confirms only afterwards", async () => {
    fetchMock.mockImplementation(async () =>
      jsonResponse({
        removable: 2,
        kept: 1,
        items: [
          { sequence: 1, entity_type: "contact", entity_id: "c1", removable: true, kept_reason: null },
          { sequence: 2, entity_type: "contract", entity_id: "k1", removable: false, kept_reason: "Es bestehen Buchungen" },
        ],
      }),
    );
    const onConfirm = vi.fn();
    renderIntl(<ImportUndoDialog importId="i1" open onConfirm={onConfirm} onCancel={vi.fn()} />);
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/bff/imports/i1/undo-preview");
    expect(await screen.findByTestId("import-undo-summary")).toBeInTheDocument();
    expect(screen.getByTestId("import-undo-kept")).toHaveTextContent("Vertrag: Es bestehen Buchungen");
    await userEvent.click(screen.getByTestId("import-undo-confirm"));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("keeps the confirmation disabled and shows the error when the preview fails", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ code: "X", title: "Vorschau fehlgeschlagen", status: 500 }, 500));
    renderIntl(<ImportUndoDialog importId="i1" open onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByTestId("import-undo-confirm")).toBeDisabled();
  });

  it("calls onCancel", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ removable: 0, kept: 0, items: [] }));
    const onCancel = vi.fn();
    renderIntl(<ImportUndoDialog importId="i1" open onConfirm={vi.fn()} onCancel={onCancel} />);
    await screen.findByTestId("import-undo-summary");
    await userEvent.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(onCancel).toHaveBeenCalled();
  });
});
