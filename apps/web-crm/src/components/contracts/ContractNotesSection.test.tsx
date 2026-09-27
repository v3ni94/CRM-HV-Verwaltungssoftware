import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ContractNotesSection } from "./ContractNotesSection";

const contract = { id: "22222222-2222-4222-8222-222222222222", notes: null, dunning_block: false, dunning_block_reason: null };

describe("ContractNotesSection", () => {
  afterEach(() => vi.restoreAllMocks());

  it("saves remarks via PATCH /contracts/{id}/notes without If-Match", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ ...contract, notes: "Schlüssel beim Hausmeister" }));
    renderIntl(<ContractNotesSection contract={contract} canEdit />);
    await userEvent.click(screen.getByRole("button", { name: "Notizen bearbeiten" }));
    await userEvent.type(screen.getByLabelText("Notizen"), "Schlüssel beim Hausmeister");
    await userEvent.tab();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`/api/bff/contracts/${contract.id}/notes`);
    expect(init.method).toBe("PATCH");
    expect(new Headers(init.headers).get("if-match")).toBeNull();
    expect(JSON.parse(String(init.body))).toEqual({ notes: "Schlüssel beim Hausmeister" });
    await waitFor(() => expect(screen.getAllByText("Gespeichert").length).toBeGreaterThan(0));
  });

  it("requires a reason before the dunning block is sent and sends both together", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ ...contract, dunning_block: true, dunning_block_reason: "Ratenzahlung vereinbart" }));
    renderIntl(<ContractNotesSection contract={contract} canEdit />);
    await userEvent.click(screen.getByRole("button", { name: "Bearbeiten" }));
    await userEvent.click(screen.getByRole("checkbox"));
    expect(screen.getByRole("alert")).toHaveTextContent("Mahnsperre braucht eine Begründung");
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.type(screen.getByLabelText("Begründung der Mahnsperre"), "Ratenzahlung vereinbart");
    await userEvent.tab();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ dunning_block: true, dunning_block_reason: "Ratenzahlung vereinbart" });
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
    expect(screen.getByRole("checkbox")).toBeChecked();
  });

  it("shows no edit controls without contracts:update", () => {
    renderIntl(<ContractNotesSection contract={contract} canEdit={false} />);
    expect(screen.queryByRole("button", { name: "Bearbeiten" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Notizen bearbeiten" })).not.toBeInTheDocument();
  });
});
