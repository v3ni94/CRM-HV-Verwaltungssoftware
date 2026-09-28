import { render, screen } from "@testing-library/react";

import { IntlTestProvider } from "@/test/intl";

// M16-15: the case in the run detail names ledger, legal entity and property so a missing
// default account links straight to the property's bank account section, and an existing
// account still shows the object number as a link.
vi.mock("next-intl/server", async () => {
  const { default: de } = await import("../../../../../../messages/de.json");
  return {
    getTranslations: async (namespace: string) => (key: string, values: Record<string, unknown> = {}) => {
      const raw = `${namespace}.${key}`.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], de);
      if (typeof raw !== "string") throw new Error(`INSUFFICIENT_PATH ${namespace}.${key}`);
      return raw.replace(/\{(\w+)\}/g, (_, name: string) => String(values[name] ?? ""));
    },
  };
});

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }));
vi.mock("@/lib/api-server", () => ({
  serverApi: () => ({ GET: getMock }),
  redirectIfUnauthenticated: () => undefined,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const BASE_CASE = {
  id: "0199a1b2-0000-7000-8000-000000000001",
  contract_id: "0199a1b2-0000-7000-8000-000000000002",
  level: 1,
  total: "100.00",
  fee_amount: "0.00",
  status: "proposed",
  reason: null,
  due_date: "2026-03-03",
  ledger_id: "0199a1b2-0000-7000-8000-000000000003",
  legal_entity_id: "0199a1b2-0000-7000-8000-000000000004",
};

async function renderPage(cases: unknown[]) {
  getMock.mockResolvedValue({
    data: { run_date: "2026-03-20", status: "preview", totals: {}, cases },
    error: undefined,
    response: new Response("{}", { status: 200 }),
  });
  const { default: DunningRunPage } = await import("./page");
  const element = await DunningRunPage({ params: Promise.resolve({ runId: "run1" }) });
  return render(
    <IntlTestProvider>
      {element}
    </IntlTestProvider>,
  );
}

describe("DunningRunPage", () => {
  it("links to the property's bank account section when the default account is missing", async () => {
    await renderPage([
      {
        ...BASE_CASE,
        bank_account: null,
        bank_warning: "Kein Standardkonto hinterlegt.",
        property_id: "0199a1b2-0000-7000-8000-000000000005",
        property_number: "781",
      },
    ]);
    const link = screen.getByRole("link", { name: "Standardkonto am Objekt festlegen" });
    expect(link).toHaveAttribute("href", "/objekte/0199a1b2-0000-7000-8000-000000000005#bankkonten");
  });

  it("shows the property number as a link when a default account exists", async () => {
    await renderPage([
      {
        ...BASE_CASE,
        bank_account: { id: "acc1", holder: "WEG Musterhaus", iban_masked: "DE** **** **** **** 3000" },
        bank_warning: null,
        property_id: "0199a1b2-0000-7000-8000-000000000005",
        property_number: "781",
      },
    ]);
    const link = screen.getByRole("link", { name: "781" });
    expect(link).toHaveAttribute("href", "/objekte/0199a1b2-0000-7000-8000-000000000005");
    expect(screen.queryByRole("link", { name: "Standardkonto am Objekt festlegen" })).not.toBeInTheDocument();
  });

  it("shows no property link when the case has no property (ledger without object)", async () => {
    await renderPage([{ ...BASE_CASE, bank_account: null, bank_warning: "Kein Standardkonto hinterlegt.", property_id: null, property_number: null }]);
    expect(screen.queryByRole("link", { name: "Standardkonto am Objekt festlegen" })).not.toBeInTheDocument();
  });
});
