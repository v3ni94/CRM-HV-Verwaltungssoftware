import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ManagerEntitySetup, type ManagerEntityStatus } from "./ManagerEntitySetup";

const notSetUp: ManagerEntityStatus = {
  status: "nicht_eingerichtet",
  name: null,
  legal_entity_id: null,
  ledger_id: null,
  accounts_count: 0,
  created: false,
};

const setUp: ManagerEntityStatus = {
  status: "eingerichtet",
  name: "Hausverwaltung Müller GmbH",
  legal_entity_id: "01920000-0000-7000-8000-00000000a001",
  ledger_id: "01920000-0000-7000-8000-00000000a002",
  accounts_count: 27,
  created: true,
};

describe("ManagerEntitySetup", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sets up the legal entity and ledger with one click and shows the new status", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/bff/tenant/manager-entity") && method === "POST") return jsonResponse(setUp);
      return jsonResponse({ title: "unerwartet" }, 500);
    });

    renderIntl(<ManagerEntitySetup initial={notSetUp} canUpdate />);
    expect(screen.getByTestId("manager-entity-status")).toHaveTextContent("nicht eingerichtet");

    await userEvent.setup().click(screen.getByRole("button", { name: "Rechtsträger und Buchungskreis einrichten" }));

    await waitFor(() => expect(screen.getByTestId("manager-entity-status")).toHaveTextContent("eingerichtet"));
    expect(screen.getByText("Rechtsträger und Buchungskreis wurden angelegt.")).toBeInTheDocument();
    expect(screen.getByText("Hausverwaltung Müller GmbH")).toBeInTheDocument();
    expect(screen.getByText("27")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/bff/tenant/manager-entity", expect.objectContaining({ method: "POST" }));
  });

  it("offers no button without the update permission and shows the set up state read only", () => {
    renderIntl(<ManagerEntitySetup initial={notSetUp} canUpdate={false} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText("Die Einrichtung erfordert das Recht Mandanteneinstellungen ändern.")).toBeInTheDocument();
  });

  it("shows an error when the setup is refused", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ title: "Der Name der verwaltenden Gesellschaft fehlt", status: 422, detail: "Name fehlt" }, 422),
    );
    renderIntl(<ManagerEntitySetup initial={notSetUp} canUpdate />);
    await userEvent.setup().click(screen.getByRole("button"));
    await waitFor(() => expect(screen.getByTestId("manager-entity-status")).toHaveTextContent("nicht eingerichtet"));
    expect(screen.getByText(/Name fehlt/)).toBeInTheDocument();
  });
});
