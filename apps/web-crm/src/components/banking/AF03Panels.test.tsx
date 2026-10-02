import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BankConnectionsPanel } from "./BankConnectionsPanel";
import { CreditorIdsCard } from "./CreditorIdsCard";
import { DirectDebitPreview } from "./DirectDebitPreview";

const LEDGER = "0192abcd-0000-7000-8000-000000000021";
const ENTITY = "0192abcd-0000-7000-8000-000000000022";

afterEach(() => vi.restoreAllMocks());

describe("AF03 Bankmasken", () => {
  it("zeigt Verbindungen, Protokoll und Schalter und speichert den Schalter mit Begründung", async () => {
    const calls: { url: string; method: string; body?: string }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      const u = String(url);
      calls.push({ url: u, method: init?.method ?? "GET", body: init?.body as string | undefined });
      if (u.endsWith("/banking/connections"))
        return jsonResponse([{ id: "c1", connector: "fints", bank_name: "Testbank", bic: null, consent_valid_until: null, status: "active", error_message: null, has_credentials: true }]);
      if (u.endsWith("/banking/runs")) return jsonResponse([]);
      return jsonResponse({ enabled: false, engine_version: "e1", rule_version: "r1", note: "" });
    });
    renderIntl(<BankConnectionsPanel canApprove />);
    expect(await screen.findByText("Testbank")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Begründung"), "Prüfung");
    await userEvent.click(screen.getByRole("button", { name: "Einschalten" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT" && c.url.endsWith("/banking/learning"))).toBe(true));
    expect(JSON.parse(calls.find((c) => c.method === "PUT")!.body!)).toEqual({ enabled: true, reason: "Prüfung" });
  });

  it("speichert die Gläubiger-ID je Rechtsträger", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ sepa_creditor_id: "X" }));
    renderIntl(<CreditorIdsCard entities={[{ id: ENTITY, name: "HVM" }]} canUpdate canUpdateTenant={false} />);
    await userEvent.type(screen.getByLabelText("Gläubiger-Identifikationsnummer"), "DE00ZZZ00000000001");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(String(spy.mock.calls[0]![0])).toContain(`/creditor-ids/legal-entities/${ENTITY}`);
    expect(await screen.findByText("Gläubiger-ID gespeichert.")).toBeInTheDocument();
  });

  it("zeigt die Lastschriftvorschau ohne etwas anzulegen", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ creditor_id: null, collection_date: "2026-11-03", count: 2, control_sum: "150.00", items: [] }),
    );
    renderIntl(<DirectDebitPreview ledgers={[{ id: LEDGER, name: "HVM" }]} />);
    await userEvent.type(screen.getByLabelText("Vorlaufzeit in Tagen"), "5");
    await userEvent.type(screen.getByLabelText("Einzug am"), "2026-11-03");
    await userEvent.click(screen.getByRole("button", { name: "Vorschau" }));
    expect(await screen.findByText(/2 Sollstellungen einziehbar/)).toBeInTheDocument();
    expect(screen.getByRole("status").textContent).toContain("keine Gläubiger-ID");
  });
});
