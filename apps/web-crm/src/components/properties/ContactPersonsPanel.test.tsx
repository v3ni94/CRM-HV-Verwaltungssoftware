import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ContactPersonsPanel, type ContactPersonRow } from "./ContactPersonsPanel";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const PID = "0192abcd-0000-7000-8000-000000000301";
const ROW: ContactPersonRow = {
  id: "0192abcd-0000-7000-8000-000000000302",
  contact_id: "0192abcd-0000-7000-8000-000000000303",
  contact_name: "Hausmeister Krause GmbH",
  category_code: "caretaker",
  valid_from: "2026-01-01",
  valid_to: null,
  visible_in_portal_for: ["tenant"],
};

function mockFetch(calls: { url: string; method: string; body: unknown }[]) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null });
    if (url.startsWith("/api/bff/catalogs/property_contact_category"))
      return jsonResponse([
        { code: "caretaker", label: "Hausmeister", active: true },
        { code: "board", label: "Beirat", active: true },
        { code: "old", label: "Alt", active: false },
      ]);
    if (url.startsWith("/api/bff/contacts?q="))
      return jsonResponse({ items: [{ id: "0192abcd-0000-7000-8000-000000000304", display_name: "Notdienst Nord" }] });
    if (method === "POST") return jsonResponse({ ...ROW, id: "new" }, 201);
    return jsonResponse({ ...ROW, valid_to: "2026-09-28" });
  });
}

describe("ContactPersonsPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    refresh.mockReset();
  });

  it("lists contact persons with name link, category label, validity and portal audience", async () => {
    mockFetch([]);
    renderIntl(<ContactPersonsPanel propertyId={PID} rows={[ROW]} canEdit={false} />);
    expect(screen.getByRole("link", { name: "Hausmeister Krause GmbH" })).toHaveAttribute("href", `/kontakte/${ROW.contact_id}`);
    await waitFor(() => expect(screen.getByText("Hausmeister")).toBeInTheDocument());
    expect(screen.getByText("01.01.2026")).toBeInTheDocument();
    expect(screen.getByText("Mieter")).toBeInTheDocument();
    expect(screen.queryByText("Ansprechpartner zuordnen")).toBeNull();
  });

  it("shows the empty state", () => {
    mockFetch([]);
    renderIntl(<ContactPersonsPanel propertyId={PID} rows={[]} canEdit />);
    expect(screen.getByText("Keine Ansprechpartner erfasst.")).toBeInTheDocument();
  });

  it("assigns a contact after search with category and audience", async () => {
    const calls: { url: string; method: string; body: unknown }[] = [];
    mockFetch(calls);
    const user = userEvent.setup();
    renderIntl(<ContactPersonsPanel propertyId={PID} rows={[]} canEdit />);
    await user.click(screen.getByRole("button", { name: "Ansprechpartner zuordnen" }));
    await user.type(screen.getByTestId("contact-person-search"), "Not");
    await user.click(await screen.findByRole("button", { name: "Notdienst Nord" }));
    const assign = screen.getByRole("button", { name: "Zuordnen" });
    expect(assign).toBeDisabled();
    await waitFor(() => expect(screen.getByRole("option", { name: "Beirat" })).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText("Kategorie"), "board");
    await user.click(screen.getByLabelText("Eigentümer"));
    expect(assign).toBeEnabled();
    await user.click(assign);
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const post = calls.find((c) => c.method === "POST");
    expect(post?.url).toBe(`/api/bff/properties/${PID}/contacts`);
    expect(post?.body).toMatchObject({
      contact_id: "0192abcd-0000-7000-8000-000000000304",
      category_code: "board",
      visible_in_portal_for: ["owner"],
      valid_to: null,
    });
  });

  it("ends an assignment with today's date via PATCH", async () => {
    const calls: { url: string; method: string; body: unknown }[] = [];
    mockFetch(calls);
    const user = userEvent.setup();
    renderIntl(<ContactPersonsPanel propertyId={PID} rows={[ROW]} canEdit />);
    await user.click(screen.getByRole("button", { name: "Beenden" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const patch = calls.find((c) => c.method === "PATCH");
    expect(patch?.url).toBe(`/api/bff/properties/${PID}/contacts/${ROW.id}`);
    expect((patch?.body as { valid_to: string }).valid_to).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("shows the problem message when the API refuses", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.startsWith("/api/bff/catalogs/")) return jsonResponse([]);
      if (init?.method === "PATCH") return jsonResponse({ title: "Eingaben ungültig", detail: "valid_to liegt vor valid_from", status: 422 }, 422);
      return jsonResponse({});
    });
    const user = userEvent.setup();
    renderIntl(<ContactPersonsPanel propertyId={PID} rows={[ROW]} canEdit />);
    await user.click(screen.getByRole("button", { name: "Beenden" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("valid_to liegt vor valid_from");
    expect(refresh).not.toHaveBeenCalled();
  });
});
