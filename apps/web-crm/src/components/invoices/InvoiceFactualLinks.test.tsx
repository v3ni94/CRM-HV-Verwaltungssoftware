import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { EMPTY_FACTUAL_LINKS, InvoiceFactualLinks, type FactualLinks } from "./InvoiceFactualLinks";

const LEDGER = "0192abcd-0000-7000-8000-000000000b01";
const ENTITY = "0192abcd-0000-7000-8000-000000000b02";
const PROVIDER = "0192abcd-0000-7000-8000-000000000b03";

function route(url: string) {
  if (url.startsWith("/api/bff/work-orders")) return jsonResponse([{ id: "w1", description: "Dach reparieren", status: "approved" }]);
  if (url.startsWith("/api/bff/hoa/resolutions")) return jsonResponse([{ id: "r1", number: 3, subject: "Dachsanierung", decided_on: "2026-03-01" }]);
  if (url === `/api/bff/hoa/plans?ledger_id=${LEDGER}`) return jsonResponse([{ id: "p1", year: 2026, version: 1, title: null, status: "resolved" }]);
  if (url === "/api/bff/hoa/plans/p1") return jsonResponse({ id: "p1", items: [{ id: "i1", label: "Instandhaltung", component: "cost", amount: "1200.00" }] });
  if (url.startsWith("/api/bff/accounting/recurring-invoices")) return jsonResponse([{ id: "rp1", text: "Wartung Aufzug", gross: "119.00", ended_at: null }]);
  return jsonResponse({}, 404);
}

function Harness({ legalEntityId = ENTITY, onValue }: { legalEntityId?: string | null; onValue: (v: FactualLinks) => void }) {
  const [v, setV] = useState<FactualLinks>(EMPTY_FACTUAL_LINKS);
  return (
    <InvoiceFactualLinks
      ledgerId={LEDGER}
      legalEntityId={legalEntityId}
      providerId={PROVIDER}
      value={v}
      onChange={(n) => {
        setV(n);
        onValue(n);
      }}
    />
  );
}

describe("InvoiceFactualLinks", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads nothing until opened, then offers order, resolution, plan item and recurring plan", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => route(String(input)));
    const seen: FactualLinks[] = [];
    renderIntl(<Harness onValue={(v) => seen.push(v)} />);
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.click(screen.getByText("Verknüpfungen für die sachliche Prüfung"));
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Auftrag" }), "w1");
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Beschluss" }), "r1");
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Rechnungsplan" }), "rp1");
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Wirtschaftsplan" }), "p1");
    await userEvent.selectOptions(await screen.findByRole("option", { name: /Instandhaltung/ }).then((o) => o.closest("select") as HTMLSelectElement), "i1");
    expect(seen.at(-1)).toEqual({ work_order_id: "w1", resolution_id: "r1", plan_item_id: "i1", recurring_plan_id: "rp1" });
    const urls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(urls).toContain(`/api/bff/work-orders?page_size=200&provider_contact_id=${PROVIDER}`);
    expect(urls).toContain(`/api/bff/hoa/resolutions?legal_entity_id=${ENTITY}`);
  });

  it("explains a missing legal entity and shows a failed list without blocking the others", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.startsWith("/api/bff/work-orders")) return jsonResponse({ title: "Verboten", status: 403, detail: "Keine Berechtigung." }, 403);
      return route(url);
    });
    renderIntl(<Harness legalEntityId={null} onValue={() => undefined} />);
    await userEvent.click(screen.getByText("Verknüpfungen für die sachliche Prüfung"));
    expect(await screen.findByText(/Liste konnte nicht geladen werden/)).toBeInTheDocument();
    expect(screen.getByText(/kein Rechtsträger bekannt/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("option", { name: /Wartung Aufzug/ })).toBeInTheDocument());
    expect(screen.getByText("Zuerst einen Wirtschaftsplan wählen.")).toBeInTheDocument();
  });
});
