import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, messages, renderIntl } from "@/test/intl";

import { Prospects } from "./Prospects";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
vi.mock("./ProspectViewings", () => ({ ProspectViewings: () => null }));
vi.mock("@/components/aj17/ProspectSelfDisclosureLinks", () => ({ ProspectSelfDisclosureLinks: () => null }));

const m = messages.Prospects;
const ROWS = [{ id: "pr1", contact_id: "c1", status: "new", delete_after: "2027-01-31", notes: null }];
const NAMES = { c1: "Erika Muster" };

type Call = { url: string; method: string; body: unknown };

function mockApi(handler: (url: string, method: string) => Response | undefined = () => undefined) {
  const calls: Call[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    return handler(url, method) ?? jsonResponse({});
  });
  return calls;
}

describe("Prospects", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    refresh.mockClear();
  });

  it("shows the contact name and the deletion date and patches the status", async () => {
    const calls = mockApi();
    renderIntl(<Prospects unitId="u1" rows={ROWS} names={NAMES} />);
    expect(screen.getByText("Erika Muster")).toBeInTheDocument();
    expect(screen.getByText("löschen nach 31.01.2027")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: m.status }), "viewing");
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(calls[0]).toEqual({ url: "/api/bff/letting/prospects/pr1", method: "PATCH", body: { status: "viewing" } });
  });

  it("deletes only after the confirmation", async () => {
    const calls = mockApi();
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    renderIntl(<Prospects unitId="u1" rows={ROWS} names={NAMES} />);
    await userEvent.click(screen.getByRole("button", { name: m.delete }));
    expect(calls).toEqual([]);
    await userEvent.click(screen.getByRole("button", { name: m.delete }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]).toMatchObject({ url: "/api/bff/letting/prospects/pr1", method: "DELETE" });
    expect(confirm).toHaveBeenCalledWith(m.confirmDelete);
  });

  it("requires contact search of two characters, a contact and a deletion date before creating", async () => {
    const calls = mockApi((url) => (url.startsWith("/api/bff/contacts") ? jsonResponse({ items: [{ id: "c9", display_name: "Max Neu" }] }) : undefined));
    renderIntl(<Prospects unitId="u1" rows={[]} names={{}} />);
    const add = screen.getByRole("button", { name: m.add });
    expect(add).toBeDisabled();
    expect(screen.getByRole("button", { name: m.search })).toBeDisabled();
    await userEvent.type(screen.getByLabelText(m.searchContact), "Ne");
    await userEvent.click(screen.getByRole("button", { name: m.search }));
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: m.contact }), "c9");
    expect(add).toBeDisabled();
    await userEvent.type(screen.getByLabelText(m.deleteAfterLabel), "2027-02-01");
    expect(add).toBeEnabled();
    await userEvent.click(add);
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.url).toBe("/api/bff/letting/prospects");
    expect(post.body).toEqual({ unit_id: "u1", contact_id: "c9", delete_after: "2027-02-01" });
    expect(calls[0]!.url).toBe("/api/bff/contacts?q=Ne");
  });

  it("rejects with a template and shows the rejection text without sending anything", async () => {
    const calls = mockApi((url) => {
      if (url.endsWith("/rejection-templates")) return jsonResponse([{ id: "tp1", label: "Standardabsage", text: "x" }]);
      if (url.endsWith("/reject")) return jsonResponse({ rejection_text: "Leider müssen wir absagen." });
      return undefined;
    });
    renderIntl(<Prospects unitId="u1" rows={ROWS} names={NAMES} />);
    await userEvent.click(screen.getByRole("button", { name: m.reject }));
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: m.rejectChoose }), "tp1");
    expect(await screen.findByDisplayValue("Leider müssen wir absagen.")).toHaveAttribute("readonly");
    const reject = calls.find((c) => c.url.endsWith("/reject"))!;
    expect(reject).toMatchObject({ url: "/api/bff/letting/prospects/pr1/reject", method: "POST", body: { template_id: "tp1" } });
  });

  it("creates a self disclosure link and shows the portal url", async () => {
    mockApi((url) => (url.endsWith("/self-disclosure-link") ? jsonResponse({ portal_url: "https://portal.example/s/abc", expires_at: "2026-11-01" }) : undefined));
    renderIntl(<Prospects unitId="u1" rows={ROWS} names={NAMES} />);
    await userEvent.click(screen.getByRole("button", { name: m.selfDisclosureLink }));
    expect(await screen.findByDisplayValue("https://portal.example/s/abc")).toBeInTheDocument();
  });

  it("shows the API error when a change is refused and does not refresh", async () => {
    mockApi(() => jsonResponse({ title: "Verboten", status: 403, detail: "Keine Berechtigung" }, 403));
    renderIntl(<Prospects unitId="u1" rows={ROWS} names={NAMES} />);
    await userEvent.selectOptions(screen.getByRole("combobox", { name: m.status }), "applied");
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });
});
