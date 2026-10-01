import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AssetReportDispatch } from "./AssetReportDispatch";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

describe("AssetReportDispatch", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    refresh.mockClear();
  });

  it("dispatches only to owners without portal retrieval by default and reports the result", async () => {
    const calls: { url: string; body: unknown }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      calls.push({ url: String(input), body: JSON.parse(String(init?.body)) });
      return jsonResponse({ created: [{ contract_id: "c1" }], skipped: [{ contract_id: "c2", reason: "retrieved_in_portal" }] }, 201);
    });
    renderIntl(<AssetReportDispatch reportId="r1" note="Hinweis zum Versand" />);
    expect(screen.getByText("Hinweis zum Versand")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Bericht per Brief versenden" }));
    await waitFor(() => expect(screen.getByText("1 Briefe vorbereitet, 1 Einheiten übersprungen")).toBeInTheDocument());
    expect(calls).toEqual([{ url: "/api/bff/hoa/asset-reports/r1/dispatch", body: { only_without_retrieval: true } }]);
    expect(refresh).toHaveBeenCalled();
  });

  it("includes owners with portal retrieval when the option is chosen", async () => {
    const bodies: unknown[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      bodies.push(JSON.parse(String(init?.body)));
      return jsonResponse({ created: [], skipped: [] }, 201);
    });
    renderIntl(<AssetReportDispatch reportId="r1" note="" />);
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Bericht per Brief versenden" }));
    await waitFor(() => expect(bodies).toEqual([{ only_without_retrieval: false }]));
  });

  it("shows the error and does not refresh when the gate or the status refuses", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ title: "Freigabestufe G4 geschlossen", status: 403 }, 403));
    renderIntl(<AssetReportDispatch reportId="r1" note="" />);
    await userEvent.click(screen.getByRole("button", { name: "Bericht per Brief versenden" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });
});
