import { fireEvent, screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PrivacyRegisterEditor, type RegisterEntryFull } from "./PrivacyRegisterEditor";

const BASE: RegisterEntryFull = {
  id: "a1",
  kind: "processing_activity",
  name: "Hausgeldabrechnung",
  role: null,
  purpose: "Abrechnung",
  data_categories: ["Name"],
  data_subjects: [],
  recipients: null,
  third_country: false,
  third_country_status: "open",
  third_country_countries: null,
  third_country_note: null,
  avv_status: "none",
  avv_confirmed_on: null,
  avv_document_id: null,
  retention_note: null,
  legal_review_status: "open",
  legal_reviewed_on: null,
  active: true,
  legal_basis: null,
  responsibilities: { gdwe: "controller" },
  responsibility_note: null,
  processor_ids: [],
  source_key: null,
  source_detail: null,
};

function body(fetchMock: { mock: { calls: unknown[][] } }) {
  const call = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/privacy/register/a1"));
  return JSON.parse(String((call?.[1] as RequestInit).body));
}

describe("PrivacyRegisterEditor", () => {
  afterEach(() => vi.restoreAllMocks());

  it("starts open, saves roles, legal basis and processors of an activity", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ ...BASE }));
    const onSaved = vi.fn();
    renderIntl(<PrivacyRegisterEditor entry={BASE} processors={[{ id: "p1", name: "Google Gmail" }]} onSaved={onSaved} onCancel={() => undefined} />);
    expect(screen.getByLabelText("Verwalter")).toHaveValue("open");
    expect(screen.getByLabelText("GdWE")).toHaveValue("controller");
    expect(screen.getByLabelText("Drittlandübermittlung")).toHaveValue("open");
    fireEvent.change(screen.getByLabelText("Verwalter"), { target: { value: "processor" } });
    fireEvent.change(screen.getByLabelText("Rechtsgrundlage"), { target: { value: "Eintrag nach Prüfung" } });
    fireEvent.click(screen.getByLabelText("Google Gmail"));
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const sent = body(fetchMock);
    expect(sent.responsibilities).toEqual({ gdwe: "controller", verwalter: "processor" });
    expect(sent.legal_basis).toBe("Eintrag nach Prüfung");
    expect(sent.processor_ids).toEqual(["p1"]);
    expect(sent.third_country_status).toBe("open");
    expect(sent.third_country).toBe(false);
  });

  it("shows third country and AVV fields for a provider, no roles", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({}));
    const provider = { ...BASE, id: "a1", kind: "sub_processor", name: "LetterXpress", responsibilities: {}, source_key: "postal:letterxpress", source_detail: "Aus Mandantenkonfiguration erkannt." };
    renderIntl(<PrivacyRegisterEditor entry={provider} processors={[]} onSaved={() => undefined} onCancel={() => undefined} />);
    expect(screen.queryByLabelText("Rechtsgrundlage")).not.toBeInTheDocument();
    expect(screen.getByTestId("privacy-register-origin")).toHaveTextContent("Aus Mandantenkonfiguration erkannt.");
    fireEvent.change(screen.getByLabelText("Drittlandübermittlung"), { target: { value: "yes" } });
    fireEvent.change(screen.getByLabelText("Länder"), { target: { value: "USA" } });
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const sent = body(fetchMock);
    expect(sent.third_country).toBe(true);
    expect(sent.third_country_countries).toBe("USA");
    expect(sent.responsibilities).toEqual({});
    expect(sent.processor_ids).toEqual([]);
  });

  it("shows the API error and keeps the form", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ code: "MHVP-PRIV-0004", title: "Registereintrag unvollständig oder widersprüchlich", status: 422 }), {
        status: 422,
        headers: { "content-type": "application/problem+json" },
      }),
    );
    const onSaved = vi.fn();
    renderIntl(<PrivacyRegisterEditor entry={BASE} processors={[]} onSaved={onSaved} onCancel={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(onSaved).not.toHaveBeenCalled();
  });
});
