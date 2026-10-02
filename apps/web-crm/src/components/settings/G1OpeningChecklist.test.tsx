import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { G1OpeningChecklist, type G1OpeningState } from "./G1OpeningChecklist";

const base: G1OpeningState = {
  chart: { released: false, code: "a1", version: 1, released_at: null, status: "draft" },
  cases: [
    { item_key: "D04", title: "Interner Banktransfer", status: "open", confirmed_on: null, confirmed_by_name: null, note: null },
    { item_key: "D05", title: "Echte Gleichzahlungen", status: "passed", confirmed_on: "2026-09-29", confirmed_by_name: "T. Müller", note: null },
  ],
  cases_total: 23,
  cases_passed: 1,
  manual: [{ item_key: "vat_review", title: "Umsatzsteuer geprüft", status: "open", confirmed_on: null, confirmed_by_name: null, note: null }],
  manual_total: 5,
  manual_passed: 0,
  automation_levels: { debtor_full: "L0", transfer_pair: "L1" },
  learning_bookkeeper_enabled: false,
  gate_open: false,
  open_request: null,
  requests: [],
  can_request: true,
  documents: { "abnahme-anhang-d": "docs/acceptance/abnahme-anhang-d.md" },
};

describe("G1OpeningChecklist", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the acceptance register state read only with a link", () => {
    renderIntl(
      <G1OpeningChecklist
        initial={{ ...base, acceptance_register: { link: "/plattform/abnahme", cases_total: 58, released_total: 3, passed_total: 2, g1_cases_total: 23, g1_passed: 2, note: "x" } }}
        canRecord={false}
        canRequest={false}
      />,
    );
    expect(screen.getByTestId("g1-register")).toHaveTextContent("G1 Fälle bestanden 2 von 23, freigegebene Sollwerte 3 von 58");
    expect(screen.getByRole("link", { name: "Zum Abnahmeregister" }).getAttribute("href")).toBe("/plattform/abnahme");
  });

  it("shows the derived state, records a result and reloads", async () => {
    let state = base;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/g1-opening/items/D04") && init?.method === "PUT") {
        state = {
          ...base,
          cases_passed: 2,
          cases: [{ ...base.cases[0]!, status: "passed", confirmed_on: "2026-09-29", confirmed_by_name: "Prüferin" }, base.cases[1]!],
        };
        return jsonResponse({ ...base.cases[0], status: "passed", confirmed_on: "2026-09-29", confirmed_by_name: "Prüferin" });
      }
      if (url.endsWith("/accounting/g1-opening")) return jsonResponse(state);
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<G1OpeningChecklist initial={base} canRecord canRequest />);
    expect(screen.getByTestId("g1-chart")).toHaveTextContent("Kontenrahmen nicht freigegeben (Status Entwurf)");
    expect(screen.getByTestId("g1-cases")).toHaveTextContent("1 von 23");
    expect(screen.getByTestId("g1-manual")).toHaveTextContent("0 von 5");
    expect(screen.getByTestId("g1-levels")).toHaveTextContent("debtor_full L0, transfer_pair L1");
    expect(screen.getByTestId("g1-gate")).toHaveTextContent("geschlossen");
    expect(screen.getByText("docs/acceptance/abnahme-anhang-d.md")).toBeInTheDocument();
    expect(screen.getByText("29.09.2026")).toBeInTheDocument();

    const user = userEvent.setup();
    const buttons = screen.getAllByRole("button", { name: "Ergebnis eintragen" });
    await user.click(buttons[0]!);
    expect(screen.getByText("Ergebnis für D04")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Name der bestätigenden Person"), "Prüferin");
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(screen.getByText("Ergebnis eingetragen.")).toBeInTheDocument());
    const call = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/items/D04"));
    expect(call?.[1]?.method).toBe("PUT");
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ status: "passed", confirmed_by_name: "Prüferin" });
    await waitFor(() => expect(screen.getByTestId("g1-cases")).toHaveTextContent("2 von 23"));
  }, 20000);

  it("files the G1 request through the gate flow and then shows it as pending", async () => {
    let state = base;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/g1-opening/request") && init?.method === "POST") {
        const request = { id: "r1", status: "requested", scope: "Produktive Buchführung HVM", requested_by: "u1", four_eyes: true };
        state = { ...base, open_request: request, requests: [request], can_request: false };
        return jsonResponse(request, 201);
      }
      if (url.endsWith("/accounting/g1-opening")) return jsonResponse(state);
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<G1OpeningChecklist initial={base} canRecord canRequest />);
    const user = userEvent.setup();
    const submit = screen.getByRole("button", { name: "Antrag auf G1 stellen" });
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText("Freigegebener Funktionsumfang und Objektgruppe"), "Produktive Buchführung HVM");
    expect(submit).toBeEnabled();
    await user.click(submit);
    await waitFor(() => expect(screen.getByText(/Antrag auf G1 gestellt/)).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bff/accounting/g1-opening/request",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ scope: "Produktive Buchführung HVM", comment: null }) }),
    );
    await waitFor(() => expect(screen.getByTestId("g1-open-request")).toHaveTextContent("Produktive Buchführung HVM"));
    expect(screen.getByTestId("g1-gate")).toHaveTextContent("beantragt, Entscheidung offen");
    expect(screen.getByText("Ein Antrag ist bereits offen.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Antrag auf G1 stellen" })).not.toBeInTheDocument();
  });

  it("hides recording and request without the rights", () => {
    renderIntl(<G1OpeningChecklist initial={base} canRecord={false} canRequest={false} />);
    expect(screen.queryByRole("button", { name: "Ergebnis eintragen" })).not.toBeInTheDocument();
    expect(screen.getByText("Der Antrag erfordert das Recht Freigabestufen beantragen.")).toBeInTheDocument();
  });
});
