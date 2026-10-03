import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { RentIncreaseBlock } from "./RentIncreaseBlock";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
const ID = "01920000-0000-7000-8000-0000000000c1";

describe("RentIncreaseBlock", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders nothing before apply", () => {
    const { container } = renderIntl(<RentIncreaseBlock caseId={ID} status="consented" proposal={null} blockSet={null} canRecord />);
    expect(container.querySelector("[data-testid=rent-increase-block]")).toBeNull();
  });

  it("shows the proposal and confirms it", async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      calls.push(`${init?.method} ${String(input)} ${String(init?.body)}`);
      return jsonResponse({});
    });
    renderIntl(<RentIncreaseBlock caseId={ID} status="applied" proposal="2027-12-01" blockSet={null} canRecord />);
    expect(screen.getByText(/01\.12\.2027/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Sperre übernehmen" }));
    await waitFor(() => expect(calls[0]).toContain('"action":"set_block","block_until":"2027-12-01"'));
    expect(refresh).toHaveBeenCalled();
  });

  it("states that no duration is configured and hides the form without permission", () => {
    renderIntl(<RentIncreaseBlock caseId={ID} status="applied" proposal={null} blockSet={null} canRecord={false} />);
    expect(screen.getByText(/Kein Vorschlag/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
