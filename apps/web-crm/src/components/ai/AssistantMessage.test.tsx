import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Message } from "@/lib/ai";
import { jsonResponse, renderIntl } from "@/test/intl";

import { AssistantMessage } from "./AssistantMessage";

const RUN = "01920000-0000-7000-8000-00000000000a";
const message = {
  id: "01920000-0000-7000-8000-00000000000b",
  conversation_id: "01920000-0000-7000-8000-00000000000c",
  role: "assistant",
  content: "Die Ruhezeiten sind 13 bis 15 Uhr.",
  document_ids: [],
  task_run_id: RUN,
  proposal_id: null,
  links: [],
  created_at: "2026-09-29T08:00:00Z",
} as unknown as Message;
const run = {
  id: RUN,
  task: "answer_question",
  status: "succeeded",
  provider: "anthropic",
  model: "m",
  prompt_version: "v1",
  output: { answer: "x" },
  confidence: null,
  tokens_in: 1,
  tokens_out: 1,
  cost_eur: "0",
  duration_ms: 1,
  error: null,
  feedback: null,
  knowledge_ids: [],
};

/** Audit 29.09.2026: "hilfreich / nicht hilfreich" on a chat answer goes to
 *  POST /ai/runs/{id}/feedback and the pressed state follows the stored verdict. */
describe("AssistantMessage feedback", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends the verdict and marks the pressed button", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith(`/api/bff/ai/runs/${RUN}/feedback`)) {
        expect(init?.method).toBe("POST");
        expect(JSON.parse(String(init?.body))).toEqual({ helpful: true });
        return jsonResponse({ ...run, feedback: "helpful" });
      }
      if (url.endsWith(`/api/bff/ai/runs/${RUN}`)) return jsonResponse(run);
      throw new Error(`unexpected ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderIntl(
      <ul>
        <AssistantMessage message={message} />
      </ul>,
    );
    const helpful = await screen.findByRole("button", { name: "Hilfreich" });
    expect(helpful).toHaveAttribute("aria-pressed", "false");
    await act(async () => {
      await userEvent.click(helpful);
    });
    expect(screen.getByRole("button", { name: "Hilfreich" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Nicht hilfreich" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText("Danke, Rückmeldung gespeichert.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/feedback"))).toBe(true);
  });

  it("shows no feedback buttons for a failed run", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ ...run, status: "failed", error: "x" })),
    );
    renderIntl(
      <ul>
        <AssistantMessage message={message} />
      </ul>,
    );
    await screen.findByText("Die Ruhezeiten sind 13 bis 15 Uhr.");
    expect(screen.queryByRole("button", { name: "Hilfreich" })).not.toBeInTheDocument();
  });
});
