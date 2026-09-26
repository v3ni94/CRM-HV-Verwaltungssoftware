import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AuditCreateForm } from "./AuditCreateForm";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push }) }));
const ENTITY = "0192abcd-0000-7000-8000-000000000101";
const CONTACT = "0192abcd-0000-7000-8000-000000000102";

describe("AuditCreateForm", () => {
  afterEach(() => vi.restoreAllMocks());

  it("requires an auditor before sending", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const user = userEvent.setup();
    renderIntl(<AuditCreateForm legalEntityId={ENTITY} statements={[]} accounts={[]} basePath="/weg/p1" />);
    await user.click(screen.getByRole("button", { name: "Prüfauftrag anlegen" }));
    await user.type(screen.getByLabelText("Zweck"), "Stichprobe 2025");
    await user.click(screen.getByRole("button", { name: "Prüfauftrag anlegen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte mindestens einen Prüfer auswählen.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("searches the auditor, sends the engagement and opens it", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      if (String(input).startsWith("/api/bff/contacts?")) return jsonResponse({ items: [{ id: CONTACT, display_name: "Erika Beirat" }] });
      return jsonResponse({ id: "audit-1" }, 201);
    });
    const user = userEvent.setup();
    renderIntl(
      <AuditCreateForm
        legalEntityId={ENTITY}
        statements={[{ id: "st1", label: "2025 · V1 · Entwurf" }]}
        accounts={[{ id: "a1", number: "040300", name: "Reinigungskosten" }]}
        basePath="/weg/p1"
      />,
    );
    await user.click(screen.getByRole("button", { name: "Prüfauftrag anlegen" }));
    await user.type(screen.getByLabelText("Zweck"), "Stichprobe 2025");
    await user.selectOptions(screen.getByLabelText("Bezug auf Abrechnung (optional)"), "st1");
    await user.selectOptions(screen.getByLabelText("Konten der Grundgesamtheit (optional)"), "040300");
    await user.type(screen.getByLabelText("Prüfer (Beirat) suchen"), "Erika");
    await user.click(screen.getByRole("button", { name: "Suchen" }));
    await user.click(await screen.findByRole("button", { name: "Erika Beirat" }));
    expect(screen.getByLabelText("Prüfer")).toHaveTextContent("Erika Beirat");
    await user.click(screen.getByRole("button", { name: "Prüfauftrag anlegen" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/weg/p1/pruefung/audit-1"));
    const contactCall = String(fetchMock.mock.calls[0]?.[0]);
    expect(contactCall).toContain("q=Erika");
    expect(contactCall).toContain("page_size=10");
    const create = fetchMock.mock.calls[1]!;
    expect(String(create[0])).toBe("/api/bff/hoa/audits");
    expect(JSON.parse(String(create[1]?.body))).toEqual({
      legal_entity_id: ENTITY,
      period_from: `${new Date().getFullYear() - 1}-01-01`,
      period_to: `${new Date().getFullYear() - 1}-12-31`,
      purpose: "Stichprobe 2025",
      sampling: "sample",
      statement_id: "st1",
      accounts: ["040300"],
      auditor_contact_ids: [CONTACT],
    });
  });
});
