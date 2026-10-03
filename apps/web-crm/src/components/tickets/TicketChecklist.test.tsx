import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, messages, renderIntl } from "@/test/intl";

import { TicketChecklist } from "./TicketChecklist";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const m = messages.Tickets;
const ITEMS = [
  { key: "a", label: "Zähler fotografiert", required: true, done: false },
  { key: "b", label: "Mieter informiert", required: false, done: true },
];

describe("TicketChecklist", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    refresh.mockClear();
  });

  it("renders nothing without checklist and extra fields", () => {
    const { container } = renderIntl(<TicketChecklist ticketId="t1" checklist={[]} extraFieldDefs={[]} extraFieldValues={{}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("toggles an item with the inverted done flag and refreshes", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}));
    renderIntl(<TicketChecklist ticketId="t1" checklist={ITEMS} extraFieldDefs={[]} extraFieldValues={{}} />);
    expect(screen.getByRole("heading", { name: m.checklist })).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("Zähler fotografiert"));
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/bff/tickets/t1/checklist/a");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual({ done: true });
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("shows the API error and does not refresh when a toggle is refused", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Fehler", status: 422, detail: "Pflichtpunkt offen" }, 422));
    renderIntl(<TicketChecklist ticketId="t1" checklist={ITEMS} extraFieldDefs={[]} extraFieldValues={{}} />);
    await userEvent.click(screen.getByLabelText("Mieter informiert"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("saves an extra field value, and an emptied value as null", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}));
    renderIntl(
      <TicketChecklist
        ticketId="t1"
        checklist={[]}
        extraFieldDefs={[{ key: "zaehler", label: "Zählernummer", required: true, type: "text" }]}
        extraFieldValues={{ zaehler: "Z-1" }}
      />,
    );
    const input = screen.getByDisplayValue("Z-1");
    await userEvent.clear(input);
    await userEvent.click(screen.getByRole("button", { name: m.saveField }));
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/bff/tickets/t1");
    expect(JSON.parse(String(init?.body))).toEqual({ extra_fields: { zaehler: null } });
    await userEvent.type(input, "Z-2");
    await userEvent.click(screen.getByRole("button", { name: m.saveField }));
    expect(JSON.parse(String(fetchMock.mock.calls[1]![1]?.body))).toEqual({ extra_fields: { zaehler: "Z-2" } });
  });
});
