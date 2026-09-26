import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { ContactOut } from "@/lib/contact-schema";
import { jsonResponse, renderIntl } from "@/test/intl";

import { ContactForm } from "./ContactForm";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh: vi.fn(), back: vi.fn() }),
}));

const ID = "01920000-0000-7000-8000-00000000000a";

function contact(overrides: Partial<ContactOut> = {}): ContactOut {
  return {
    id: ID,
    kind: "person",
    display_name: "Erika Mustermann",
    salutation: null,
    title: null,
    first_name: "Erika",
    last_name: "Mustermann",
    company_name: null,
    legal_form: null,
    position: null,
    date_of_birth: null,
    language: "de",
    notes: null,
    preferred_channel: null,
    blocked: false,
    external_ids: {},
    completeness: "complete",
    addresses: [],
    phones: [],
    emails: [],
    identifiers: [],
    bank_accounts: [],
    types: [],
    roles: [],
    tags: [],
    version: 3,
    created_at: "2026-09-01T10:00:00Z",
    updated_at: "2026-09-01T10:00:00Z",
    deleted_at: null,
    ...overrides,
  };
}

describe("ContactForm", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    push.mockReset();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("requires a name for persons and a company name for companies", async () => {
    renderIntl(<ContactForm mode="create" />);
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(
      await screen.findByText("Personen benötigen Vor- oder Nachname."),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("Firma"));
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(
      await screen.findByText("Firmen benötigen einen Firmennamen."),
    ).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("validates e-mail and IBAN in the repeatable groups", async () => {
    renderIntl(<ContactForm mode="create" />);
    await userEvent.type(screen.getByLabelText("Nachname"), "Mustermann");
    await userEvent.click(
      screen.getByRole("button", { name: "E-Mail-Adressen: Hinzufügen" }),
    );
    await userEvent.type(screen.getByLabelText("E-Mail"), "falsch@");
    await userEvent.click(
      screen.getByRole("button", { name: "Bankverbindungen: Hinzufügen" }),
    );
    await userEvent.type(
      screen.getByLabelText("IBAN"),
      "DE89370400440532013001",
    );
    await userEvent.type(screen.getByLabelText("BIC"), "XYZ");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(
      await screen.findByText("Bitte eine gültige E-Mail-Adresse eingeben."),
    ).toBeInTheDocument();
    expect(screen.getByText("Die IBAN ist ungültig.")).toBeInTheDocument();
    expect(screen.getByText("Die BIC ist ungültig.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("checks duplicates first and saves only after confirmation", async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse([
          {
            contact: {
              ...contact(),
              city: null,
              primary_email: null,
              primary_phone: null,
              deleted: false,
            },
            score: 0.8,
            reasons: ["ähnlicher Name"],
          },
        ]),
      )
      .mockResolvedValueOnce(jsonResponse(contact(), 201));
    renderIntl(<ContactForm mode="create" />);
    await userEvent.type(screen.getByLabelText("Vorname"), "Erika");
    await userEvent.type(screen.getByLabelText("Nachname"), "Mustermann");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByText("Mögliche Dubletten")).toBeInTheDocument();
    expect(String(fetchMock.mock.calls[0]![0])).toBe(
      "/api/bff/contacts/duplicates?first_name=Erika&last_name=Mustermann",
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await userEvent.click(
      screen.getByRole("button", { name: "Trotzdem speichern" }),
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/kontakte/${ID}`));
    const [url, init] = fetchMock.mock.calls[1]!;
    expect(url).toBe("/api/bff/contacts");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toMatchObject({
      kind: "person",
      first_name: "Erika",
      last_name: "Mustermann",
    });
  });

  it("maps API field errors to the form fields", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([])).mockResolvedValueOnce(
      jsonResponse(
        {
          title: "Eingaben ungültig",
          status: 422,
          detail: "Bitte die markierten Angaben prüfen.",
          errors: [
            {
              location: ["body", "phones", 0, "number"],
              field: "number",
              code: "value_error",
              message: "Telefonnummer ist ungültig.",
            },
          ],
        },
        422,
      ),
    );
    renderIntl(<ContactForm mode="create" />);
    await userEvent.type(screen.getByLabelText("Nachname"), "Mustermann");
    await userEvent.click(
      screen.getByRole("button", { name: "Telefonnummern: Hinzufügen" }),
    );
    await userEvent.type(screen.getByLabelText("Nummer"), "0211 1234");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(
      await screen.findByText("Telefonnummer ist ungültig."),
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Bitte die markierten Angaben prüfen.",
    );
  });

  it("sends If-Match on edit and explains a version conflict (412)", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { title: "Datensatz wurde zwischenzeitlich geändert", status: 412 },
        412,
      ),
    );
    renderIntl(<ContactForm mode="edit" contact={contact()} />);
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Der Datensatz wurde zwischenzeitlich geändert. Bitte die Seite neu laden",
    );
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe(`/api/bff/contacts/${ID}`);
    expect(init?.method).toBe("PUT");
    expect(new Headers(init?.headers).get("if-match")).toBe('"3"');
  });

  it("saves a contact with bank accounts without resubmitting them", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(contact(), 200));
    renderIntl(
      <ContactForm
        mode="edit"
        contact={contact({
          bank_accounts: [
            {
              id: ID,
              label: null,
              iban_masked: "DE89 **** **** 3000",
              bic: null,
              bank_name: null,
              holder: null,
              valid_from: "2026-01-01",
              valid_to: null,
              sepa_enabled: false,
              mandate_reference: null,
              mandate_signed_on: null,
              mandate_granted_via: null,
              mandate_note: null,
              mandate_document_id: null,
              mandate_scheme: "core",
              mandate_status: "active",
              mandate_revoked_on: null,
              approval_status: "approved",
            },
          ],
        })}
      />,
    );
    expect(screen.getByText("DE89 **** **** 3000")).toBeInTheDocument();
    const save = screen.getByRole("button", { name: "Speichern" });
    expect(save).toBeEnabled();
    await userEvent.click(save);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const init = fetchMock.mock.calls[0]![1]!;
    expect(init.method).toBe("PUT");
    expect(JSON.parse(String(init.body))).not.toHaveProperty("bank_accounts");
  });

  it("requires signing date, granted via and a document or note when SEPA is enabled", async () => {
    renderIntl(<ContactForm mode="create" />);
    await userEvent.type(screen.getByLabelText("Nachname"), "Mustermann");
    await userEvent.click(
      screen.getByRole("button", { name: "Bankverbindungen: Hinzufügen" }),
    );
    await userEvent.type(
      screen.getByLabelText("IBAN"),
      "DE89370400440532013000",
    );
    await userEvent.click(screen.getByLabelText("SEPA-Lastschrift aktiv"));
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(
      await screen.findByText("Bitte das Datum der Erteilung angeben."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Bitte die Erteilungsart angeben."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Bitte das Mandat als PDF hinterlegen oder einen Vermerk eintragen.",
      ),
    ).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("submits the SEPA mandate fields for a new bank account", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse(contact(), 201));
    renderIntl(<ContactForm mode="create" />);
    await userEvent.type(screen.getByLabelText("Nachname"), "Mustermann");
    await userEvent.click(
      screen.getByRole("button", { name: "Bankverbindungen: Hinzufügen" }),
    );
    await userEvent.type(
      screen.getByLabelText("IBAN"),
      "DE89370400440532013000",
    );
    await userEvent.click(screen.getByLabelText("SEPA-Lastschrift aktiv"));
    await userEvent.type(
      screen.getByLabelText("Mandatsreferenz"),
      "M-2026-001",
    );
    await userEvent.type(
      screen.getByLabelText("Datum der Erteilung"),
      "2026-09-01",
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Erteilungsart"),
      "email",
    );
    await userEvent.type(
      screen.getByLabelText("Vermerk"),
      "Per E-Mail bestätigt",
    );
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const body = JSON.parse(String(fetchMock.mock.calls[1]![1]!.body));
    expect(body.bank_accounts).toMatchObject([
      {
        iban: "DE89370400440532013000",
        sepa_enabled: true,
        mandate_reference: "M-2026-001",
        mandate_signed_on: "2026-09-01",
        mandate_granted_via: "email",
        mandate_note: "Per E-Mail bestätigt",
        mandate_scheme: "core",
      },
    ]);
  });

  it("submits the selected roles", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse(contact(), 201));
    renderIntl(<ContactForm mode="create" />);
    await userEvent.type(screen.getByLabelText("Nachname"), "Mustermann");
    const rolesGroup = screen.getByRole("group", { name: "Klassifizierung" });
    await userEvent.click(within(rolesGroup).getByLabelText("Mieter"));
    await userEvent.click(within(rolesGroup).getByLabelText("Eigentümer"));
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const body = JSON.parse(String(fetchMock.mock.calls[1]![1]!.body));
    expect(body.roles.sort()).toEqual(["eigentuemer", "mieter"]);
  });
});
