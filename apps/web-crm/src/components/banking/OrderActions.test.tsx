import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { OrderActions } from "./OrderActions";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

describe("OrderActions", () => {
  afterEach(() => vi.restoreAllMocks());

  it("approves a draft and shows the four eyes refusal", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({ title: "Vier Augen", status: 403, detail: "Zweite Freigabe durch eine andere Person." }, 403),
    );
    renderIntl(<OrderActions id="0192abcd-0000-7000-8000-000000000009" status="draft" />);
    await userEvent.click(screen.getByText("Freigeben"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("offers nothing for executed orders", () => {
    const { container } = renderIntl(<OrderActions id="x" status="executed" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("cancels only after confirmation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}));
    vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    renderIntl(<OrderActions id="0192abcd-0000-7000-8000-000000000009" status="approved" />);
    await userEvent.click(screen.getByText("Verwerfen"));
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.click(screen.getByText("Verwerfen"));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });
});
