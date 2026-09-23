import { act, screen } from "@testing-library/react";

import type { Run } from "@/lib/ai";
import { jsonResponse, renderIntl } from "@/test/intl";

import { RunProgress } from "./RunProgress";

const base: Run = {
  id: "01920000-0000-7000-8000-0000000000r3",
  task: "extract_contacts",
  status: "queued",
  provider: null,
  model: null,
  prompt_version: "1",
  output: null,
  confidence: null,
  tokens_in: 0,
  tokens_out: 0,
  cost_eur: "0",
  duration_ms: 0,
  error: null,
  proposal_id: null,
};

describe("RunProgress", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("polls every 2 s while queued or running and stops when done", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ ...base, status: "running" }))
      .mockResolvedValueOnce(jsonResponse({ ...base, status: "succeeded" }));
    vi.stubGlobal("fetch", fetchMock);
    const onDone = vi.fn();
    renderIntl(<RunProgress run={base} onDone={onDone} />);
    expect(screen.getByRole("status")).toHaveTextContent("eingereiht");
    await act(async () => vi.advanceTimersByTimeAsync(1999));
    expect(fetchMock).not.toHaveBeenCalled();
    await act(async () => vi.advanceTimersByTimeAsync(1));
    expect(fetchMock).toHaveBeenCalledWith(`/api/bff/ai/runs/${base.id}`, expect.anything());
    expect(screen.getByRole("status")).toHaveTextContent("arbeitet");
    await act(async () => vi.advanceTimersByTimeAsync(2000));
    expect(onDone).toHaveBeenCalledWith(expect.objectContaining({ status: "succeeded" }));
    await act(async () => vi.advanceTimersByTimeAsync(6000));
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("shows the blocked reason", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => jsonResponse({ ...base, status: "blocked", error: "Monatsbudget ausgeschöpft" })));
    renderIntl(<RunProgress run={base} />);
    await act(async () => vi.advanceTimersByTimeAsync(2000));
    expect(screen.getByRole("alert")).toHaveTextContent("Auftrag gesperrt");
    expect(screen.getByRole("alert")).toHaveTextContent("Monatsbudget ausgeschöpft");
  });

  it("shows the failure reason of a finished run without polling", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<RunProgress run={{ ...base, status: "failed", error: "Schemafehler" }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Auftrag fehlgeschlagen");
    expect(screen.getByRole("alert")).toHaveTextContent("Schemafehler");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
