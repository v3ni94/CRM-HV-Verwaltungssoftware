import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ProviderSettings } from "./ProviderSettings";

const provider = {
  provider: "anthropic",
  models: { small: { model: "m-small", input_eur_per_mtok: "1", output_eur_per_mtok: "5" } },
  task_tiers: {},
  monthly_budget_eur: "10",
  data_processing_agreement_signed: false,
  dpa_document_id: null,
  training_opt_out_confirmed: false,
  endpoint_region: null,
  enabled: false,
  has_api_key: true,
  released_at: null,
};

describe("ProviderSettings tool use", () => {
  afterEach(() => vi.restoreAllMocks());

  it("is off by default, offered for prompt tiers only and sent only when on", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(provider, 200));
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    renderIntl(<ProviderSettings provider="anthropic" initial={provider as any} />);
    const boxes = screen.getAllByRole("checkbox", { name: /Werkzeuge \(Tool Use\)/ });
    expect(boxes).toHaveLength(2);
    expect(boxes[0]!).not.toBeChecked();
    expect(screen.getAllByText(/Vier-Augen-Prinzip/).length).toBeGreaterThan(0);
    await userEvent.click(boxes[0]!);
    await userEvent.click(screen.getByRole("button", { name: /speichern/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
    const body = JSON.parse(String(put?.[1]?.body));
    expect(body.models.small.tool_use).toBe(true);
  });

  it("omits tool_use when the switch stays off", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(provider, 200));
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    renderIntl(<ProviderSettings provider="anthropic" initial={provider as any} />);
    await userEvent.click(screen.getByRole("button", { name: /speichern/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(JSON.parse(String(put?.[1]?.body)).models.small.tool_use).toBeUndefined();
  });
});
