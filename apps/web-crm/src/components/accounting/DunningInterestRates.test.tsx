import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DunningInterestRates } from "./DunningInterestRates";

describe("DunningInterestRates", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists the history and records a new rate with source", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      if (init?.method === "POST") return jsonResponse({ id: "r2" }, 201);
      return jsonResponse([{ id: "r1", valid_from: "2026-01-01", valid_to: null, base_rate: "2.27", source: "Bundesbank" }]);
    });
    renderIntl(<DunningInterestRates />);
    expect(await screen.findByText("Bundesbank")).toBeInTheDocument();
    expect(screen.getByText("offen")).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "Satz erfassen" });
    expect(button).toBeDisabled();
    const box = screen.getByTestId("dunning-rates");
    await userEvent.type(box.querySelector('input[type="date"]') as HTMLInputElement, "2026-07-01");
    const inputs = box.querySelectorAll("input:not([type=date])");
    await userEvent.type(inputs[0] as HTMLInputElement, "1,75");
    await userEvent.type(inputs[1] as HTMLInputElement, "Bundesbank Juli");
    await userEvent.click(button);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Basiszinssatz erfasst."));
    const post = fetchMock.mock.calls.find(([, i]) => i?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ valid_from: "2026-07-01", base_rate: "1.75", source: "Bundesbank Juli" });
  });
});
