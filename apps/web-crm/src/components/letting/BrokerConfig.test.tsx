import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, messages, renderIntl } from "@/test/intl";

import { BrokerConfig } from "./BrokerConfig";

const m = messages.Af20.broker;
const config = { provider: "flowfact", enabled: false, api_key_set: true, base_url: "https://api.example.test", last_test_ok: null, last_test_message: "Test ok" };

describe("BrokerConfig", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads the config without showing the key and saves a new key write-only", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_u, init) =>
      jsonResponse(init?.method === "PUT" ? { ...config, enabled: true } : config),
    );
    renderIntl(<BrokerConfig canManage />);
    const url = await screen.findByDisplayValue("https://api.example.test");
    expect(url).toBeInTheDocument();
    expect(screen.getByText(m.apiKeySet)).toBeInTheDocument();
    expect(screen.getByText("Test ok")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText(m.enabled));
    await userEvent.type(screen.getByLabelText(m.apiKeySet), "geheim");
    await userEvent.click(screen.getByRole("button", { name: m.save }));
    expect(await screen.findByRole("status")).toHaveTextContent(m.saved);
    const put = fetchMock.mock.calls.find((c) => c[1]?.method === "PUT")!;
    expect(String(put[0])).toBe("/api/bff/letting/broker/flowfact/config");
    expect(JSON.parse(String(put[1]?.body))).toEqual({ enabled: true, base_url: "https://api.example.test", api_key: "geheim" });
    expect(screen.getByLabelText(m.apiKeySet)).toHaveValue("");
  });

  it("omits the api key when untouched and shows the API refusal", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_u, init) =>
      init?.method === "PUT" ? jsonResponse({ title: "Fehler", status: 422, detail: "Basis URL ungültig" }, 422) : jsonResponse(config),
    );
    renderIntl(<BrokerConfig canManage />);
    await screen.findByDisplayValue("https://api.example.test");
    await userEvent.click(screen.getByRole("button", { name: m.save }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Basis URL ungültig");
    const put = fetchMock.mock.calls.find((c) => c[1]?.method === "PUT")!;
    expect(JSON.parse(String(put[1]?.body))).not.toHaveProperty("api_key");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("is read only without manage right", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(config));
    renderIntl(<BrokerConfig canManage={false} />);
    await screen.findByDisplayValue("https://api.example.test");
    await waitFor(() => expect(screen.getByRole("button", { name: m.save })).toBeDisabled());
    expect(screen.getByLabelText(m.enabled)).toBeDisabled();
    expect(screen.getByLabelText(m.baseUrl)).toBeDisabled();
  });
});
