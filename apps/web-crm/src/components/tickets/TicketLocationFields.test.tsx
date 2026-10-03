import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, messages, renderIntl } from "@/test/intl";

import { BuildingSelect, PropertyPicker } from "./TicketLocationFields";

const m = messages.TicketLocation;

describe("PropertyPicker", () => {
  afterEach(() => vi.restoreAllMocks());

  it("does not search below two characters", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderIntl(<PropertyPicker onPick={vi.fn()} />);
    await userEvent.type(screen.getByLabelText(m.propertySearch), "a");
    expect(screen.getByRole("button", { name: m.search })).toBeDisabled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("searches, lists results and reports the picked property", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ items: [{ id: "p1", number: "101", name: "Am Park", extra: 1 }] }));
    const onPick = vi.fn();
    renderIntl(<PropertyPicker onPick={onPick} />);
    await userEvent.type(screen.getByLabelText(m.propertySearch), "Park{Enter}");
    expect(String(fetchMock.mock.calls[0]![0])).toBe("/api/bff/properties?q=Park&page_size=10");
    await userEvent.click(await screen.findByRole("button", { name: "101 Am Park" }));
    expect(onPick).toHaveBeenCalledWith({ id: "p1", number: "101", name: "Am Park" });
    expect(screen.queryByRole("button", { name: "101 Am Park" })).toBeNull();
  });

  it("shows the error of a failed search", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Fehler", status: 500, detail: "Suche gescheitert" }, 500));
    renderIntl(<PropertyPicker onPick={vi.fn()} />);
    await userEvent.type(screen.getByLabelText(m.propertySearch), "Park");
    await userEvent.click(screen.getByRole("button", { name: m.search }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("BuildingSelect", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads the buildings of the property and reports the choice", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([{ id: "b1", name: "Haus 1" }]));
    const onChange = vi.fn();
    renderIntl(<BuildingSelect propertyId="p1" value="" onChange={onChange} />);
    expect(screen.getByRole("combobox")).toBeDisabled();
    await screen.findByRole("option", { name: "Haus 1" });
    expect(String(fetchMock.mock.calls[0]![0])).toBe("/api/bff/properties/p1/buildings");
    await userEvent.selectOptions(screen.getByRole("combobox"), "b1");
    expect(onChange).toHaveBeenCalledWith("b1");
    expect(screen.getByRole("option", { name: m.noBuilding })).toBeInTheDocument();
  });

  it("falls back to only the empty option when loading fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "x", status: 500 }, 500));
    renderIntl(<BuildingSelect propertyId="p1" value="" onChange={vi.fn()} />);
    expect(await screen.findByRole("option", { name: m.noBuilding })).toBeInTheDocument();
    expect(screen.getAllByRole("option")).toHaveLength(1);
  });
});
