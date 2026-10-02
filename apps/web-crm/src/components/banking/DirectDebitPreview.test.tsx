import { act, fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DirectDebitPreview } from "./DirectDebitPreview";

const ledgers = [{ id: "l1", name: "WEG Nord" }];

async function fill() {
  fireEvent.change(screen.getByLabelText("Einzug am"), { target: { value: "2026-10-15" } });
  await userEvent.type(screen.getByLabelText("Vorlaufzeit in Tagen"), "5");
  await act(async () => {
    await userEvent.click(screen.getByRole("button", { name: "Vorschau" }));
  });
}

describe("DirectDebitPreview", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders nothing without ledgers", () => {
    const { container } = renderIntl(<DirectDebitPreview ledgers={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("posts the preview request and shows the result", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ creditor_id: null, collection_date: "2026-10-15", count: 3, control_sum: "300.00", items: [] }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<DirectDebitPreview ledgers={ledgers} />);
    await fill();
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/accounting/direct-debits/preview");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ ledger_id: "l1", collection_date: "2026-10-15", lead_days: 5 });
    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("3 Sollstellungen");
    expect(status).toHaveTextContent("15.10.2026");
    expect(status).toHaveTextContent("keine Gläubiger-ID");
  });

  it("shows the API error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Fehler", status: 422, detail: "x" }, 422)));
    renderIntl(<DirectDebitPreview ledgers={ledgers} />);
    await fill();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
