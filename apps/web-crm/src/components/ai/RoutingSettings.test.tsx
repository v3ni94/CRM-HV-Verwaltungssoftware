import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { RoutingSettings } from "./RoutingSettings";

describe("RoutingSettings", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders the initial strategy and saves a change via PUT /ai/routing", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ strategy: "openai_only" }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<RoutingSettings initial="anthropic_first" />);
    const select = screen.getByRole("combobox") as HTMLSelectElement;
    expect(select.value).toBe("anthropic_first");
    await act(async () => {
      await userEvent.selectOptions(select, "openai_only");
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/ai/routing");
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("PUT");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ strategy: "openai_only" });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows the problem message when the API refuses (403)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "Nur Administratoren" }, 403)));
    renderIntl(<RoutingSettings initial="alternate" />);
    await act(async () => {
      await userEvent.selectOptions(screen.getByRole("combobox"), "anthropic_only");
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
