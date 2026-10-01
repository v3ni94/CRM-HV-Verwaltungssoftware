import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DepositInterestPanel } from "./DepositInterestPanel";

const ID = "01920000-0000-7000-8000-00000000000a";
const DRAFT = "01920000-0000-7000-8000-00000000000b";

describe("DepositInterestPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows rates and drafts and confirms a draft", async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (url.endsWith(`/deposits/${ID}/interest-rates`)) return jsonResponse([{ id: "r1", valid_from: "2025-01-01", rate: "1.00000", note: null }]);
      if (url.endsWith(`/deposits/${ID}/interest-drafts`)) return jsonResponse([{ id: DRAFT, year: 2025, rate: "1.00000", days: 365, amount: "12.00", status: "draft" }]);
      if (url.endsWith(`/deposit-interest-drafts/${DRAFT}/confirm`)) return jsonResponse({});
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<DepositInterestPanel depositId={ID} canUpdate />);
    expect(await screen.findByText("01.01.2025")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Bestätigen" }));
    await waitFor(() => expect(calls).toContain(`POST /api/bff/deposit-interest-drafts/${DRAFT}/confirm`));
  });

  it("offers no actions without update permission", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([]));
    renderIntl(<DepositInterestPanel depositId={ID} canUpdate={false} />);
    expect(await screen.findByText(/Kein Zinssatz hinterlegt/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Entwurf berechnen" })).toBeNull();
  });
});
