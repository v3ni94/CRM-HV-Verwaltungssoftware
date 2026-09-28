import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ContactForm } from "@/components/contacts/ContactForm";
import { PropertyCreate } from "@/components/properties/PropertyCreate";
import { DataQualityReport } from "@/components/settings/DataQualityReport";
import { TicketCreate, TicketEdit } from "@/components/tickets/TicketForms";
import { checkContact, checkDeadline, checkProperty, isPastDate, postcodeInvalid } from "@/lib/entry-standards";
import { jsonResponse, renderIntl } from "@/test/intl";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn(), back: vi.fn() }) }));
const ID = "01920000-0000-7000-8000-00000000000a";
const ids = (f: { rule: string }[]) => f.map((x) => x.rule);

describe("entry standards rules (mirror of mhvp.dataquality.rules)", () => {
  it("checks the German postcode only", () => {
    expect(postcodeInvalid("DE", "40789")).toBe(false);
    expect(postcodeInvalid("DE", "4078")).toBe(true);
    expect(postcodeInvalid(null, "D-40789")).toBe(true);
    expect(postcodeInvalid("AT", "1010")).toBe(false);
    expect(postcodeInvalid("DE", "")).toBe(false);
  });

  it("checks property address and name pattern", () => {
    expect(checkProperty({ name: "Rheinpromenade 13, 40789 Monheim am Rhein", street: "Rheinpromenade", house_number: "13", postal_code: "40789", city: "Monheim am Rhein" })).toEqual([]);
    expect(ids(checkProperty({ name: "WEG Monheim", street: "Rheinpromenade 13", postal_code: "4078" }))).toEqual(["ES-01", "ES-02", "ES-02", "ES-03", "ES-04"]);
  });

  it("checks contact names like the API", () => {
    expect(ids(checkContact({ kind: "person", first_name: "Anna", last_name: "Schmidt" }))).toEqual([]);
    expect(ids(checkContact({ kind: "person", first_name: "", last_name: "von Bülow" }))).toEqual(["ES-08"]);
    expect(ids(checkContact({ kind: "person", last_name: "Anna Schmidt" }))).toEqual(["ES-06"]);
    expect(ids(checkContact({ kind: "person", last_name: "Schmidt, Anna" }))).toEqual(["ES-05"]);
    expect(ids(checkContact({ kind: "person", first_name: "", last_name: "Muster GmbH" }))).toEqual(["ES-06", "ES-07"]);
    expect(ids(checkContact({ kind: "company", company_name: "Muster GmbH" }))).toEqual([]);
  });

  it("checks deadlines against the local day", () => {
    const today = new Date(2026, 8, 28);
    expect(isPastDate("2026-09-27", today)).toBe(true);
    expect(isPastDate("2026-09-28", today)).toBe(false);
    expect(ids(checkDeadline({ due_on: "2026-09-27" }, today))).toEqual(["ES-09", "ES-10"]);
    expect(checkDeadline({ due_on: "2026-10-01", assignee_user_id: "u" }, today)).toEqual([]);
  });
});

describe("form hints", () => {
  afterEach(() => vi.restoreAllMocks());

  it("property create: blocks an invalid postcode, warns softly and applies the name suggestion", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: ID }, 201));
    renderIntl(<PropertyCreate />);
    await userEvent.type(screen.getByLabelText("Objektnummer (3 Ziffern)"), "101");
    await userEvent.type(screen.getByLabelText("Name"), "Monheim");
    await userEvent.type(screen.getByLabelText("Straße"), "Rheinpromenade");
    await userEvent.type(screen.getByLabelText("PLZ"), "4078");
    expect(screen.getByRole("alert")).toHaveTextContent("genau fünf Ziffern");
    expect(screen.getByText("Anlegen")).toBeDisabled();
    await userEvent.type(screen.getByLabelText("PLZ"), "9");
    await userEvent.type(screen.getByLabelText("Hausnummer"), "13");
    await userEvent.type(screen.getByLabelText("Ort"), "Monheim am Rhein");
    const hints = screen.getByTestId("property-create-hints");
    expect(hints).toHaveTextContent("Vorschlag: Rheinpromenade 13, 40789 Monheim am Rhein");
    // Warnings do not block saving.
    expect(screen.getByText("Anlegen")).toBeEnabled();
    await userEvent.click(within(hints).getByText("Vorschlag übernehmen"));
    expect(screen.getByLabelText("Name")).toHaveValue("Rheinpromenade 13, 40789 Monheim am Rhein");
    expect(screen.queryByTestId("property-create-hints")).toBeNull();
    await userEvent.click(screen.getByText("Anlegen"));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/objekte/${ID}`));
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string).postal_code).toBe("40789");
  });

  it("contact form: hints on 'Vorname Name' in the last name field", async () => {
    renderIntl(<ContactForm mode="create" />);
    await userEvent.type(screen.getByLabelText("Nachname"), "Anna Schmidt");
    expect(screen.getByTestId("contact-name-hints")).toHaveTextContent("Im Feld Nachname steht vermutlich Vorname und Nachname");
    await userEvent.type(screen.getByLabelText("Vorname"), "Anna");
    await userEvent.clear(screen.getByLabelText("Nachname"));
    await userEvent.type(screen.getByLabelText("Nachname"), "Schmidt");
    expect(screen.queryByTestId("contact-name-hints")).toBeNull();
  });

  it("ticket create: a past due date needs an explicit confirmation", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      if (String(input).includes("/tickets/templates")) return jsonResponse([]);
      return jsonResponse({ id: ID }, 201);
    });
    renderIntl(<TicketCreate />);
    await userEvent.type(screen.getByLabelText("Titel"), "Heizung defekt");
    await userEvent.type(screen.getByLabelText("Fälligkeit"), "2020-01-31");
    expect(screen.getByText("Ticket anlegen")).toBeDisabled();
    expect(screen.getByText(/verantwortliche Person/)).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText(/Ich bestätige das Datum ausdrücklich/));
    expect(screen.getByText("Ticket anlegen")).toBeEnabled();
  });

  it("ticket edit: a past due date is saved only after confirmation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}));
    renderIntl(<TicketEdit id={ID} status="new" priority="normal" />);
    await userEvent.type(screen.getByLabelText("Fälligkeit"), "2020-01-31");
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.click(screen.getByText("Vergangenes Datum bestätigen"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ due_on: "2020-01-31" });
  });
});

describe("DataQualityReport", () => {
  it("lists sections with links to fix the records", () => {
    renderIntl(
      <DataQualityReport
        report={{
          generated_on: "2026-09-28",
          sections_omitted: ["deadlines"],
          sections: [
            {
              key: "properties",
              total: 1,
              items: [{ entity_type: "property", entity_id: ID, label: "101 Monheim", findings: [{ rule: "ES-02", field: "city", severity: "warning", message: "Ort fehlt." }] }],
            },
            { key: "contacts", total: 0, items: [] },
          ],
        }}
      />,
    );
    expect(screen.getByText("Stand 28.09.2026", { exact: false })).toBeInTheDocument();
    const props = screen.getByTestId("dq-properties");
    expect(within(props).getByText("Warnung ES-02: Ort fehlt.")).toBeInTheDocument();
    expect(within(props).getByRole("link", { name: "Öffnen" })).toHaveAttribute("href", `/objekte/${ID}`);
    expect(within(screen.getByTestId("dq-contacts")).getByText("Keine Abweichungen gefunden.")).toBeInTheDocument();
    expect(screen.getByText(/Ohne Berechtigung ausgeblendet: Fristen ohne verantwortliche Person/)).toBeInTheDocument();
  });

  it("shows an error when the report could not be loaded", () => {
    renderIntl(<DataQualityReport report={null} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Der Bericht konnte nicht geladen werden.");
  });
});
