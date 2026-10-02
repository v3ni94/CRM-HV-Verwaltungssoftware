import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ImportUndoButton } from "./ImportUndoButton";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }), usePathname: () => "/importe", useSearchParams: () => new URLSearchParams() }));

const PREVIEW = {
  import_id: "imp-1",
  removable: 2,
  kept: 1,
  items: [
    { sequence: 1, entity_type: "contact", entity_id: "c1", removable: true, kept_reason: null },
    { sequence: 2, entity_type: "unit", entity_id: "u1", removable: true, kept_reason: null },
    { sequence: 3, entity_type: "contract", entity_id: "k1", removable: false, kept_reason: "Kaution erfasst" },
  ],
};

function route(undoResponse: Response = jsonResponse({})) {
  return vi.fn((url: string, init?: RequestInit) => Promise.resolve(url.endsWith("/undo-preview") ? jsonResponse(PREVIEW) : (void init, undoResponse)));
}

describe("ImportUndoButton", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    refresh.mockReset();
  });

  it("shows the preview with kept reasons in a dialog and does not call window.confirm", async () => {
    const confirm = vi.spyOn(window, "confirm");
    const fetchMock = route();
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<ImportUndoButton id="imp-1" />);
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Rückgängig" }));
    });
    expect(await screen.findByTestId("import-undo-summary")).toHaveTextContent("2 Datensätze werden entfernt");
    expect(screen.getByTestId("import-undo-kept")).toHaveTextContent("Vertrag: Kaution erfasst");
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/imports/imp-1/undo-preview");
    expect(confirm).not.toHaveBeenCalled();
    expect(fetchMock.mock.calls.some((c) => String(c[0]).endsWith("/undo"))).toBe(false);
  });

  it("posts to the undo BFF path only after confirmation in the dialog and refreshes", async () => {
    const fetchMock = route();
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<ImportUndoButton id="imp-1" />);
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Rückgängig" }));
    });
    await screen.findByTestId("import-undo-summary");
    await act(async () => {
      await userEvent.click(screen.getByTestId("import-undo-confirm"));
    });
    const call = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/undo"));
    expect(call?.[0]).toBe("/api/bff/imports/imp-1/undo");
    expect(call?.[1]?.method).toBe("POST");
    expect(refresh).toHaveBeenCalled();
  });

  it("does not call the undo API when the dialog is cancelled", async () => {
    const fetchMock = route();
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<ImportUndoButton id="imp-1" />);
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Rückgängig" }));
    });
    await screen.findByTestId("import-undo-summary");
    await userEvent.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(fetchMock.mock.calls.some((c) => String(c[0]).endsWith("/undo"))).toBe(false);
  });

  it("shows the error for a forbidden request (403) and does not refresh", async () => {
    vi.stubGlobal("fetch", route(jsonResponse({ title: "Forbidden", status: 403, detail: "Keine Berechtigung" }, 403)));
    renderIntl(<ImportUndoButton id="imp-1" />);
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Rückgängig" }));
    });
    await screen.findByTestId("import-undo-summary");
    await act(async () => {
      await userEvent.click(screen.getByTestId("import-undo-confirm"));
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });
});
