import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { EnergyCertificateForm } from "./EnergyCertificateForm";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const PROPERTY = {
  id: "0192abcd-0000-7000-8000-000000000063",
  number: "768",
  name: "Energiehaus",
  management_type: "rental",
  status: "active",
  version: 3,
  legal_entities: [{ id: "le1", kind: "rental_owner", name: "Eigentümer" }],
  city: "Monheim am Rhein",
  energy_certificate_type: null,
  energy_certificate_value: null,
  energy_certificate_source: null,
  energy_certificate_construction_year: null,
  energy_certificate_issued_on: null,
  energy_certificate_valid_until: null,
  energy_certificate_class: null,
};

describe("EnergyCertificateForm", () => {
  afterEach(() => vi.restoreAllMocks());

  it("saves the certificate with the full property record and the version header", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ ...PROPERTY, version: 4 }));
    renderIntl(<EnergyCertificateForm property={PROPERTY} />);
    await userEvent.selectOptions(screen.getByLabelText("Art des Ausweises"), "bedarf");
    await userEvent.type(screen.getByLabelText("Kennwert in kWh/(m²a)"), "95.50");
    await userEvent.type(screen.getByLabelText("Energieträger"), "Gas");
    await userEvent.type(screen.getByLabelText("Baujahr laut Ausweis"), "1978");
    await userEvent.type(screen.getByLabelText("Ausstellungsdatum"), "2024-03-01");
    await userEvent.type(screen.getByLabelText("Gültig bis"), "2034-02-28");
    await userEvent.type(screen.getByLabelText("Effizienzklasse"), "D");
    await userEvent.click(screen.getByText("Energieausweis speichern"));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`/api/bff/properties/${PROPERTY.id}`);
    expect(init.method).toBe("PUT");
    expect(new Headers(init.headers).get("if-match")).toBe("3");
    const body = JSON.parse(init.body as string);
    expect(body).toMatchObject({
      number: "768",
      name: "Energiehaus",
      management_type: "rental",
      city: "Monheim am Rhein",
      energy_certificate_type: "bedarf",
      energy_certificate_value: "95.50",
      energy_certificate_source: "Gas",
      energy_certificate_construction_year: 1978,
      energy_certificate_issued_on: "2024-03-01",
      energy_certificate_valid_until: "2034-02-28",
      energy_certificate_class: "D",
    });
    expect(body).not.toHaveProperty("legal_entities");
    expect(body).not.toHaveProperty("version");
    expect(screen.getByText("Gespeichert.")).toBeInTheDocument();
  });

  it("shows the API problem on a rejected date range", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ title: "Validierung", detail: "Gültigkeit des Energieausweises liegt vor dem Ausstellungsdatum." }, 422),
    );
    renderIntl(<EnergyCertificateForm property={PROPERTY} />);
    await userEvent.click(screen.getByText("Energieausweis speichern"));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Ausstellungsdatum/);
  });
});

describe("EnergyCertificateForm validation (review 26.09.2026)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("blocks a malformed year and a validity before the issue date without calling the API", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderIntl(<EnergyCertificateForm property={PROPERTY} />);
    await userEvent.type(screen.getByLabelText("Baujahr laut Ausweis"), "78");
    await userEvent.click(screen.getByText("Energieausweis speichern"));
    expect(screen.getByRole("alert")).toHaveTextContent("Baujahr als vierstellige Jahreszahl.");
    await userEvent.clear(screen.getByLabelText("Baujahr laut Ausweis"));
    await userEvent.type(screen.getByLabelText("Ausstellungsdatum"), "2024-03-01");
    await userEvent.type(screen.getByLabelText("Gültig bis"), "2020-01-01");
    await userEvent.click(screen.getByText("Energieausweis speichern"));
    expect(screen.getByRole("alert")).toHaveTextContent("liegt vor dem Ausstellungsdatum");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends a German decimal value as a decimal string and the class in capitals", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ ...PROPERTY, version: 4 }));
    renderIntl(<EnergyCertificateForm property={PROPERTY} />);
    await userEvent.type(screen.getByLabelText("Kennwert in kWh/(m²a)"), "112,5");
    await userEvent.type(screen.getByLabelText("Effizienzklasse"), "d");
    await userEvent.click(screen.getByText("Energieausweis speichern"));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Gespeichert."));
    const body = JSON.parse(String(fetchMock.mock.calls[0]![1]?.body)) as Record<string, unknown>;
    expect(body.energy_certificate_value).toBe("112.5");
    expect(body.energy_certificate_class).toBe("D");
  });
});
