import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DunningPreviewButton } from "./DunningPreviewButton";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

describe("DunningPreviewButton", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    push.mockReset();
  });

  it("creates a dunning run for the date and opens the run page", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: "run-9" }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<DunningPreviewButton today="2026-10-02" />);
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/accounting/dunning-runs");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ run_date: "2026-10-02" });
    expect(push).toHaveBeenCalledWith("/buchhaltung/mahnwesen/run-9");
  });

  it("shows the error and stays on the page when creation is forbidden (403)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403)));
    renderIntl(<DunningPreviewButton today="2026-10-02" />);
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
