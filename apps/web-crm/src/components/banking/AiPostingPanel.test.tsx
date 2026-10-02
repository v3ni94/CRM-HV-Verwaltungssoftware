import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AiPostingPanel, AiPostingSwitch } from "./AiPostingPanel";

const proposal = {
  id: "p1",
  decision: "pending",
  created_at: "2026-09-01T10:00:00Z",
  proposed: {
    account_number: "6000",
    splits: [{ account_number: "6000", amount: "100.00", cost_object: null }],
    reasoning: "Rechnung Dach",
    confidence: 0.8,
    warnings: ["Prüfen"],
  },
  run: { provider: "p", model: "m1", prompt_version: "v1", status: "ok", cost_eur: "0.01", tokens_in: 1, tokens_out: 1 },
};

describe("AiPostingPanel", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("loads and renders proposals", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ bank_transaction_id: "t1", proposals: [proposal], note: "" })));
    renderIntl(<AiPostingPanel txId="t1" canRequest={false} />);
    expect(await screen.findByTestId("ai-posting-proposal")).toHaveTextContent("Rechnung Dach");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("requests a proposal via POST", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ bank_transaction_id: "t1", proposals: [], note: "" }))
      .mockResolvedValueOnce(jsonResponse({ bank_transaction_id: "t1", proposals: [proposal], note: "" }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<AiPostingPanel txId="t1" canRequest />);
    expect(await screen.findByText("Noch kein KI-Vorschlag.")).toBeInTheDocument();
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe("POST");
    expect(await screen.findByTestId("ai-posting-proposal")).toBeInTheDocument();
  });

  it("shows the API error when the request is refused", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ bank_transaction_id: "t1", proposals: [], note: "" }))
      .mockResolvedValueOnce(jsonResponse({ title: "Gesperrt", status: 409, detail: "Gesperrt" }, 409));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<AiPostingPanel txId="t1" canRequest />);
    await screen.findByText("Noch kein KI-Vorschlag.");
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("AiPostingSwitch", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("loads the state and shows the blocked reason", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ enabled: false, blocked_reason: "kein AVV" })));
    renderIntl(<AiPostingSwitch />);
    expect(await screen.findByText(/kein AVV/)).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).not.toBeChecked();
  });

  it("switches on with PUT", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ enabled: false, blocked_reason: null }))
      .mockResolvedValueOnce(jsonResponse({ enabled: true, blocked_reason: null }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<AiPostingSwitch />);
    await screen.findByTestId("ai-posting-switch");
    await vi.waitFor(() => expect(screen.getByRole("checkbox")).toBeEnabled());
    await act(async () => {
      await userEvent.click(screen.getByRole("checkbox"));
    });
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe("PUT");
    expect(JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string)).toEqual({ enabled: true });
    expect(screen.getByRole("checkbox")).toBeChecked();
  });

  it("shows the load error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403)));
    renderIntl(<AiPostingSwitch />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
