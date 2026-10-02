import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { StatementCreate } from "./StatementCreate";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }));

const L1 = "0192abcd-0000-7000-8000-000000000071";
const L2 = "0192abcd-0000-7000-8000-000000000072";
const NEW = "0192abcd-0000-7000-8000-000000000073";
const ledgers = [
  { id: L1, name: "Buchungskreis A" },
  { id: L2, name: "Buchungskreis B" },
];

describe("StatementCreate", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    push.mockReset();
  });

  it("creates a statement for the selected ledger and opens it", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ id: NEW }, 201));
    renderIntl(<StatementCreate ledgers={ledgers} />);
    await userEvent.selectOptions(screen.getByLabelText("Buchungskreis"), L2);
    await userEvent.click(screen.getByRole("button", { name: "Abrechnung anlegen" }));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/bff/statements");
    expect(init.method).toBe("POST");
    const year = new Date().getFullYear() - 1;
    expect(JSON.parse(String(init.body))).toEqual({ ledger_id: L2, period_from: `${year}-01-01`, period_to: `${year}-12-31` });
    expect(push).toHaveBeenCalledWith(`/abrechnung/${NEW}`);
  });

  it("requires a purpose of at least three characters for an interim statement", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ id: NEW }, 201));
    renderIntl(<StatementCreate ledgers={ledgers} />);
    const create = screen.getByRole("button", { name: "Abrechnung anlegen" });
    expect(create).toBeEnabled();
    await userEvent.click(screen.getByLabelText("Unterjährige Abrechnung (Sonderzeitraum)"));
    expect(create).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Zweck des Sonderzeitraums"), "Verkauf");
    expect(create).toBeEnabled();
    await userEvent.click(create);
    expect(JSON.parse(String((fetchMock.mock.calls[0] as [string, RequestInit])[1].body))).toMatchObject({
      ledger_id: L1,
      interim: true,
      purpose: "Verkauf",
    });
  });

  it("is disabled without ledger and shows API errors without navigating", async () => {
    const { unmount } = renderIntl(<StatementCreate ledgers={[]} />);
    expect(screen.getByRole("button", { name: "Abrechnung anlegen" })).toBeDisabled();
    unmount();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Zeitraum überschneidet sich", status: 409 }, 409));
    renderIntl(<StatementCreate ledgers={ledgers} />);
    await userEvent.click(screen.getByRole("button", { name: "Abrechnung anlegen" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
