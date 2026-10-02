import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { G5Evidence, type EvidenceList } from "./G5Evidence";

const tenants = [
  { id: "t1", name: "Mandant Eins", slug: "eins" },
  { id: "t2", name: "Mandant Zwei", slug: "zwei" },
];
const list = (over: Partial<EvidenceList> = {}): EvidenceList => ({
  tenant_id: "t1",
  items: [{ code: "avv", label: "AVV liegt vor", status: "open", done: false, document_id: null, note: null, decided_at: null }],
  complete: false,
  missing: ["avv"],
  gate_open: false,
  ...over,
});

describe("G5Evidence (GAH-407)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the empty state without data", () => {
    renderIntl(<G5Evidence tenants={[]} initial={null} />);
    expect(screen.getByText("Kein Mandant vorhanden.")).toBeInTheDocument();
  });

  it("states that the gate stays closed while items are open", () => {
    renderIntl(<G5Evidence tenants={tenants} initial={list()} />);
    expect(screen.getByText("1 Nachweise offen. G5 bleibt geschlossen.")).toBeInTheDocument();
    expect(screen.getByText("AVV liegt vor")).toBeInTheDocument();
  });

  it("shows a complete list as still closed until the superadmin approves", () => {
    renderIntl(<G5Evidence tenants={tenants} initial={list({ complete: true, missing: [] })} />);
    expect(screen.getByText(/G5 bleibt geschlossen, bis der Superadmin/)).toBeInTheDocument();
  });

  it("saves an item as done with the document id and reloads", async () => {
    fetchMock.mockImplementation(async (input, init) =>
      jsonResponse(init?.method === "PUT" ? {} : list({ complete: true, missing: [] })),
    );
    renderIntl(<G5Evidence tenants={tenants} initial={list()} />);
    await userEvent.type(screen.getByLabelText("Dokument-ID (Pflicht für erledigt)"), " doc-1 ");
    await userEvent.click(screen.getByRole("button", { name: "Als erledigt speichern" }));
    const put = fetchMock.mock.calls[0];
    expect(String(put?.[0])).toBe("/api/bff/platform/tenants/t1/g5-evidence/avv");
    expect(put?.[1]?.method).toBe("PUT");
    expect(JSON.parse(String(put?.[1]?.body))).toEqual({ status: "done", document_id: "doc-1", note: null });
    expect(await screen.findByText(/Alle Nachweise erledigt/)).toBeInTheDocument();
  });

  it("shows the refusal of the API", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ code: "X", title: "Dokument fehlt", status: 422 }, 422));
    renderIntl(<G5Evidence tenants={tenants} initial={list()} />);
    await userEvent.click(screen.getByRole("button", { name: "Als erledigt speichern" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("loads another tenant on change", async () => {
    fetchMock.mockImplementation(async () => jsonResponse(list({ tenant_id: "t2", gate_open: true })));
    renderIntl(<G5Evidence tenants={tenants} initial={list()} />);
    await userEvent.selectOptions(screen.getByLabelText("Mandant"), "t2");
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/bff/platform/tenants/t2/g5-evidence");
    expect(await screen.findByText("G5 ist für diesen Mandanten freigegeben.")).toBeInTheDocument();
  });
});
