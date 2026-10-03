import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { OwnerInspectionPanel } from "./OwnerInspectionPanel";

const LIST = {
  enabled: true,
  note: "Hinweis",
  communities: [
    { id: "e1", name: "WEG A" },
    { id: "e2", name: "WEG B" },
  ],
  items: [
    {
      id: "r1",
      legal_entity_id: "e1",
      requested_on: "2026-10-01",
      scope_kinds: ["receipts"],
      scope_text: null,
      status: "released",
      steps: [],
    },
  ],
};

describe("OwnerInspectionPanel", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders nothing while the switch is off", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ enabled: false, note: "aus", items: [] })));
    const { container } = renderIntl(<OwnerInspectionPanel />);
    await act(async () => {});
    expect(container.querySelector("section")).toBeNull();
  });

  it("lists own requests with status and date", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(LIST)));
    renderIntl(<OwnerInspectionPanel />);
    expect(await screen.findByText("freigegeben")).toBeInTheDocument();
    expect(screen.getByText(/01\.10\.2026/)).toBeInTheDocument();
  });

  it("requires a scope before posting", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(LIST));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<OwnerInspectionPanel />);
    await userEvent.click(await screen.findByRole("button", { name: "Anfrage senden" }));
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("posts the request for the chosen community", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(LIST))
      .mockResolvedValueOnce(jsonResponse({ id: "r2" }, 201))
      .mockResolvedValueOnce(jsonResponse(LIST));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<OwnerInspectionPanel />);
    await userEvent.selectOptions(await screen.findByRole("combobox"), "e2");
    await userEvent.click(screen.getByRole("checkbox", { name: "Belege" }));
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Anfrage senden" }));
    });
    const body = JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string);
    expect(body).toEqual({ legal_entity_id: "e2", scope_kinds: ["receipts"] });
    expect(await screen.findByText("Die Einsichtsanfrage wurde übermittelt.")).toBeInTheDocument();
  });

  it("shows the API error", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(LIST))
      .mockResolvedValueOnce(jsonResponse({ title: "x", status: 403, detail: "nicht freigeschaltet" }, 403));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<OwnerInspectionPanel />);
    await userEvent.type(await screen.findByRole("textbox"), "Verträge Hausmeister");
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Anfrage senden" }));
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
