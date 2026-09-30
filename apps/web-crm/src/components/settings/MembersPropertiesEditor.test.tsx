import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PropertiesEditor } from "./MembersAdmin";

const member = {
  membership_id: "m1",
  user_id: "u1",
  email: "clerk@example.org",
  display_name: "Sachbearbeitung",
  status: "active",
  roles: ["standard"],
  property_ids: [],
} as unknown as Parameters<typeof PropertiesEditor>[0]["member"];

const options = [
  { id: "p1", number: "101", name: "Rheinpromenade 13" },
  { id: "p2", number: "102", name: "Am Panke Park" },
];

describe("PropertiesEditor (M2-02)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("saves the selected properties", async () => {
    fetchMock.mockImplementation(async () => new Response(null, { status: 204 }));
    const onSaved = vi.fn();
    renderIntl(<PropertiesEditor member={member} options={options} onSaved={onSaved} />);
    await userEvent.click(screen.getByRole("button", { name: "Objekte: alle" }));
    await userEvent.click(screen.getByLabelText("101 Rheinpromenade 13"));
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(["p1"]));
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/bff/tenant/members/m1/properties");
    expect(JSON.parse(String(init?.body))).toEqual({ property_ids: ["p1"] });
  });

  it("shows the API error and keeps the editor open", async () => {
    fetchMock.mockImplementation(async () =>
      jsonResponse({ code: "MHVP-CORE-0002", detail: "Unbekannte Objekte: p9." }, 422),
    );
    renderIntl(<PropertiesEditor member={member} options={options} onSaved={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Objekte: alle" }));
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByText(/Unbekannte Objekte/)).toBeInTheDocument();
  });

  it("is hidden for administrator roles", () => {
    const admin = { ...member, roles: ["tenant_admin"] } as typeof member;
    const { container } = renderIntl(<PropertiesEditor member={admin} options={options} onSaved={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});
