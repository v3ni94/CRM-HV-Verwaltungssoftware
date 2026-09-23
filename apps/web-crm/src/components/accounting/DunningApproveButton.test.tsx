import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DunningApproveButton } from "./DunningApproveButton";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

describe("DunningApproveButton", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the refusal when the creator tries to approve", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({ title: "Vier Augen", status: 403, detail: "Die Freigabe muss eine andere Person erteilen." }, 403),
    );
    renderIntl(<DunningApproveButton runId="0192abcd-0000-7000-8000-000000000010" />);
    await userEvent.click(screen.getByText("Mahnlauf freigeben"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });
});
