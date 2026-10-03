import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, messages, renderIntl } from "@/test/intl";

import { GatedAction } from "./GatedAction";
import { GateStatusNotice } from "./GateStatusNotice";

const m = messages.gatedMasks;

function mockApi(open: boolean, post: () => Response = () => jsonResponse({ ok: true })) {
  const posts: { url: string; body: unknown }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/api/bff/tenant/release-gates")) return jsonResponse([{ gate: "G2", label: "G2", open, scopes: [] }]);
    posts.push({ url, body: init?.body });
    return post();
  });
  return posts;
}

describe("GatedAction", () => {
  afterEach(() => vi.restoreAllMocks());

  it("stays disabled with the lock text while the gate is closed and sends nothing", async () => {
    const posts = mockApi(false);
    renderIntl(<GatedAction gate="G2" url="/api/bff/x/run" label="Zahlung auslösen" lockedText="Gesperrt bis G2" testId="ga" />);
    expect(await screen.findByText("Gesperrt bis G2")).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "Zahlung auslösen" });
    expect(button).toBeDisabled();
    await userEvent.click(button);
    expect(posts).toEqual([]);
    expect(screen.getByTestId("gate-status-G2")).toHaveAttribute("data-gate-open", "false");
  });

  it("posts once with the body when the gate is open and reports success", async () => {
    const posts = mockApi(true);
    const onDone = vi.fn();
    renderIntl(<GatedAction gate="G2" url="/api/bff/x/run" label="Zahlung auslösen" lockedText="Gesperrt" body={{ id: 7 }} onDone={onDone} testId="ga" />);
    const button = screen.getByRole("button", { name: "Zahlung auslösen" });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    expect(await screen.findByRole("status")).toHaveTextContent(m.done);
    expect(posts).toHaveLength(1);
    expect(JSON.parse(String(posts[0]!.body))).toEqual({ id: 7 });
    expect(onDone).toHaveBeenCalledWith({ ok: true });
    expect(screen.queryByText("Gesperrt")).not.toBeInTheDocument();
  });

  it("shows the API refusal without success message", async () => {
    mockApi(true, () => jsonResponse({ title: "Gesperrt", status: 403, detail: "Freigabe fehlt (G2)" }, 403));
    renderIntl(<GatedAction gate="G2" url="/api/bff/x/run" label="Zahlung auslösen" lockedText="Gesperrt" testId="ga" />);
    const button = screen.getByRole("button", { name: "Zahlung auslösen" });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    expect(await screen.findByRole("alert")).toHaveTextContent("Freigabe fehlt (G2)");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("keeps the action locked when blocked is set or the gate state cannot be read", async () => {
    const posts = mockApi(true);
    const { unmount } = renderIntl(<GatedAction gate="G2" url="/api/bff/x/run" label="Los" lockedText="Gesperrt" blocked testId="ga" />);
    await screen.findByTestId("gate-status-G2");
    await waitFor(() => expect(screen.getByTestId("gate-status-G2")).toHaveAttribute("data-gate-open", "true"));
    expect(screen.getByRole("button", { name: "Los" })).toBeDisabled();
    unmount();
    vi.restoreAllMocks();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ detail: "x" }, 500));
    renderIntl(<GatedAction gate="G2" url="/api/bff/x/run" label="Los" lockedText="Gesperrt" testId="ga" />);
    expect(await screen.findByText("Gesperrt")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Los" })).toBeDisabled();
    expect(posts).toEqual([]);
  });

  it("GateStatusNotice marks the loading state as not open", () => {
    renderIntl(<GateStatusNotice gate="G1" state={{ status: "loading", label: null }} lockedText="Noch gesperrt" />);
    expect(screen.getByTestId("gate-status-G1")).toHaveAttribute("data-gate-open", "false");
    expect(screen.getByRole("note")).toHaveTextContent("Noch gesperrt");
  });
});
