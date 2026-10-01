import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DocumentPicker } from "./DocumentPicker";

describe("DocumentPicker", () => {
  afterEach(() => vi.restoreAllMocks());

  it("searches, selects and clears a document", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () =>
        jsonResponse({ items: [{ id: "d1", title: "Protokoll", filename: "p.pdf", created_at: "2026-09-01T10:00:00Z" }] }),
      );
    const onChange = vi.fn();
    renderIntl(<DocumentPicker label="Dokument" value="" onChange={onChange} />);
    expect(screen.getByText("Suchen")).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Dokumente suchen (mindestens 2 Zeichen)"), "Pro");
    await userEvent.click(screen.getByText("Suchen"));
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/api/bff/documents?q=Pro");
    await userEvent.click(await screen.findByText("Auswählen"));
    expect(onChange).toHaveBeenCalledWith("d1", "Protokoll");
  });

  it("shows no search while disabled", () => {
    renderIntl(<DocumentPicker label="Dokument" value="d1" disabled onChange={() => {}} />);
    expect(screen.getByTestId("document-picker-chosen")).toHaveTextContent("Gewähltes Dokument d1");
    expect(screen.queryByText("Suchen")).toBeNull();
  });
});
