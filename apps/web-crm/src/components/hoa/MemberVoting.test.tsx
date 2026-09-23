import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MemberVoting } from "./MemberVoting";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
const ITEM = "0192abcd-0000-7000-8000-000000000030";

describe("MemberVoting", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lets represented owners vote once and shows cast votes", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: "v" }, 201));
    renderIntl(
      <MemberVoting
        meetingId="m"
        status="held"
        agenda={[{ id: ITEM, position: 1, resolution: null }]}
        members={[
          { contract_id: "c1", unit_number: "01", party_name: "A", present: true, proxy: false, votes: {} },
          { contract_id: "c3", unit_number: "03", party_name: "B", present: false, proxy: true, votes: { [ITEM]: "no" } },
          { contract_id: "c4", unit_number: "04", party_name: "C", present: false, proxy: false, votes: {} },
        ]}
      />,
    );
    const row03 = screen.getByText("03").closest("tr") as HTMLElement;
    expect(within(row03).getByText("Nein")).toBeInTheDocument();
    expect(within(row03).queryByRole("button")).toBeNull();
    expect(screen.queryByLabelText("04 TOP 1 Ja")).toBeNull();
    await userEvent.click(screen.getByLabelText("01 TOP 1 Ja"));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ contract_id: "c1", choice: "yes" });
  });
});
