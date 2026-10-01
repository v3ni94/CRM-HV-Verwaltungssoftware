import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { ReservePlans } from "./ReservePlans";

const R = "00000000-0000-7000-8000-000000000001";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

const rows = [
  { id: "p1", year: 2026, planned_contribution: "1500.00", status: "draft", resolution_id: null, tax_classification_status: "not_released", plan_item_amount: "1500.00", deviation: "0.00" },
  { id: "p0", year: 2025, planned_contribution: "1200.00", status: "resolved", resolution_id: "r1", tax_classification_status: "not_released" },
];

describe("ReservePlans", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists plans with status and tax placeholder and resolves a draft", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(rows));
    renderIntl(<ReservePlans reserveId={R} name="Dach" resolutions={[{ id: "r1", label: "3 Wirtschaftsplan 2026" }]} />);
    expect(await screen.findByText("Entwurf")).toBeInTheDocument();
    expect(screen.getByText("Beschlossen")).toBeInTheDocument();
    expect(screen.getAllByText("Platzhalter, nicht freigegeben")).toHaveLength(2);
    expect(screen.getByText(/1\.500,00/, { selector: "td" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Als beschlossen kennzeichnen" }));
    await waitFor(() => expect(fetchMock.mock.calls.some((c) => String(c[0]) === "/api/bff/hoa/reserve-plans/p1/resolve")).toBe(true));
    const call = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/resolve"));
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ resolution_id: "r1" });
  });

  it("creates a draft with decimal comma", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([]));
    renderIntl(<ReservePlans reserveId={R} />);
    expect(await screen.findByText("Noch kein Rücklagenplan erfasst.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Soll-Zuführung"), "800,50");
    await userEvent.click(screen.getByRole("button", { name: "Plan als Entwurf anlegen" }));
    await waitFor(() => expect(fetchMock.mock.calls.some((c) => c[1]?.method === "POST")).toBe(true));
    const call = fetchMock.mock.calls.find((c) => c[1]?.method === "POST");
    expect(String(call?.[0])).toBe(`/api/bff/hoa/reserves/${R}/plans`);
    expect(JSON.parse(String(call?.[1]?.body)).planned_contribution).toBe("800.50");
  });
});
