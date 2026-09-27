import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { type MeteringConnection, type MeteringProvider } from "@/lib/metering";
import { jsonResponse, renderIntl } from "@/test/intl";

import { ConnectionWizard } from "./ConnectionWizard";

const CONN_ID = "11111111-1111-4111-8111-111111111111";

const providers: MeteringProvider[] = [
  {
    code: "ista",
    name: "ista",
    manual_only: true,
    functions: [
      { function: "documents", documented_support: "yes", label: "Ja, API vorhanden", source: "Q1", note: "", adapter_implemented: false },
      { function: "consumption", documented_support: "documentation_required", label: "Dokumentation erforderlich", source: "Q2", note: "", adapter_implemented: false },
    ],
    sources: {},
    research_note: "Recherchestand 26.09.2026",
    auth_note: "",
  },
];

const connection: MeteringConnection = {
  id: CONN_ID,
  display_name: "ista Hauptkonto",
  provider_code: "ista",
  contracting_company: null,
  environment: "test",
  status: "active",
  customer_references: ["0004711"],
  config: {},
  secret_names: ["client_id"],
  capabilities: [
    {
      function: "documents",
      documented_support: "yes",
      documented_note: "",
      adapter_implemented: false,
      supported_version: null,
      account_release: false,
      last_test_result: null,
      last_test_at: null,
      test_stale: false,
      released_by_last_test: false,
      available: false,
      reason: "Kein Adapter",
      label: "Ja, API vorhanden",
    },
  ],
  last_test_status: null,
  last_test_at: null,
  last_test_detail: null,
  test_stale: false,
  scheduled_sync_enabled: false,
  write_sync_enabled: false,
  last_sync: {},
  version: 1,
};

describe("ConnectionWizard", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows honest capability states, creates the connection with secrets and runs the test", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/metering/connections") && init?.method === "POST") return jsonResponse(connection, 201);
      if (url.endsWith(`/metering/connections/${CONN_ID}/test`))
        return jsonResponse({
          outcome: "manual",
          detail: "Kein Fernzugriff, manuelle Verbindung.",
          functions_released: [],
          connection: { ...connection, last_test_status: "manual", last_test_at: "2026-09-26T08:00:00+00:00", test_stale: true },
        });
      return jsonResponse({ detail: "unexpected" }, 500);
    });
    const onDone = vi.fn();
    renderIntl(<ConnectionWizard providers={providers} onDone={onDone} onCancel={() => undefined} />);
    expect(screen.getByText("Ja, API vorhanden")).toBeInTheDocument();
    expect(screen.getByText("Dokumentation erforderlich")).toBeInTheDocument();
    expect(screen.getByText("nur manuell")).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("radio", { name: /ista/ }));
    await user.click(screen.getByRole("button", { name: "Weiter" }));
    await user.type(screen.getByLabelText("Anzeigename"), "ista Hauptkonto");
    await user.type(screen.getByLabelText(/Kunden- und Vertragsnummern/), "0004711");
    await user.click(screen.getByRole("button", { name: "Weiter" }));
    await user.type(screen.getByLabelText("Bezeichnung (zum Beispiel client_id)"), "client_id");
    await user.type(screen.getByLabelText("Wert"), "geheim");
    await user.click(screen.getByRole("button", { name: "Verbindung anlegen" }));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
    const createCall = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/metering/connections"));
    const body = JSON.parse(String(createCall?.[1]?.body)) as { customer_references: string[]; secrets: Record<string, string> };
    expect(body.customer_references).toEqual(["0004711"]);
    expect(body.secrets).toEqual({ client_id: "geheim" });

    await user.click(screen.getByTestId("metering-run-test"));
    const result = await screen.findByTestId("metering-test-result");
    expect(result).toHaveTextContent("manuell, kein Fernzugriff");
    expect(result).toHaveTextContent("veraltet");
    expect(result).toHaveTextContent("Eine erfolgreiche Anmeldung bestätigt nicht den Zugriff auf alle Objekte");
  });
});
