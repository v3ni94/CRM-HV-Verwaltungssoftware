import { fireEvent, screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { RepresentativesPanel, type ContactRelation } from "./RepresentativesPanel";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh, back: vi.fn() }),
}));

const OWNER = "11111111-1111-7111-8111-111111111111";
const relation: ContactRelation = {
  id: "22222222-2222-7222-8222-222222222222",
  related_contact_id: "33333333-3333-7333-8333-333333333333",
  related_display_name: "Jan Müller",
  kind: "representative",
  valid_from: null,
  valid_to: null,
  delivery_mode: "both",
  direction: "outgoing",
};

describe("RepresentativesPanel", () => {
  beforeEach(() => {
    refresh.mockReset();
    vi.restoreAllMocks();
  });

  it("shows the empty state and no form without contacts:update", () => {
    renderIntl(<RepresentativesPanel contactId={OWNER} relations={[]} canEdit={false} />);
    expect(screen.getByText("Keine Bevollmächtigten hinterlegt.")).toBeInTheDocument();
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
  });

  it("lists the representative with the delivery rule and patches a change", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ ...relation, delivery_mode: "representative_only" }));
    renderIntl(<RepresentativesPanel contactId={OWNER} relations={[relation]} canEdit={true} />);
    expect(screen.getByRole("link", { name: "Jan Müller" })).toHaveAttribute("href", `/kontakte/${relation.related_contact_id}`);
    const select = screen.getByLabelText("Zustellregel für Jan Müller");
    expect(select).toHaveValue("both");
    fireEvent.change(select, { target: { value: "representative_only" } });
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`/api/bff/contacts/${OWNER}/contact-relations/${relation.id}`);
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(String(init.body))).toEqual({ delivery_mode: "representative_only", fields: ["delivery_mode"] });
  });

  it("shows whom this contact represents, read only", () => {
    renderIntl(
      <RepresentativesPanel contactId={OWNER} relations={[{ ...relation, direction: "incoming", related_display_name: "Timo Müller", delivery_mode: "owner_only" }]} canEdit={false} />,
    );
    expect(screen.getByText("Bevollmächtigt für:")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Timo Müller" })).toBeInTheDocument();
    expect(screen.getByText("(nur Vollmachtgeber)")).toBeInTheDocument();
  });

  it("ends an authorisation after confirmation", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 204 }));
    renderIntl(<RepresentativesPanel contactId={OWNER} relations={[relation]} canEdit={true} />);
    fireEvent.click(screen.getByRole("button", { name: "Vollmacht beenden" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect((fetchMock.mock.calls[0] as [string, RequestInit])[1].method).toBe("DELETE");
  });
});
