import { fireEvent, screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PropertyStatusPanel } from "./PropertyStatusPanel";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));

const ID = "11111111-1111-7111-8111-111111111111";

describe("PropertyStatusPanel (GAL-306)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("needs a confirmation before the status is posted", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ id: ID, status: "active" }));
    renderIntl(<PropertyStatusPanel propertyId={ID} status="onboarding" canEdit />);
    const apply = screen.getByRole("button", { name: "Status ändern" });
    expect(apply).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Neuer Status"), { target: { value: "active" } });
    expect(apply).toBeDisabled();
    fireEvent.click(screen.getByLabelText("Ich bestätige die Aktivierung des Objekts."));
    fireEvent.click(apply);
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const call = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(call[0]).toBe(`/api/bff/properties/${ID}/status`);
    expect(JSON.parse(String(call[1].body))).toEqual({ status: "active" });
  });

  it("shows the refusal of the API", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ detail: "Ein Objekt kann erst mit mindestens einer Einheit aktiviert werden." }, 422));
    renderIntl(<PropertyStatusPanel propertyId={ID} status="onboarding" canEdit />);
    fireEvent.change(screen.getByLabelText("Neuer Status"), { target: { value: "active" } });
    fireEvent.click(screen.getByLabelText("Ich bestätige die Aktivierung des Objekts."));
    fireEvent.click(screen.getByRole("button", { name: "Status ändern" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("renders nothing without edit right or for a terminated property", () => {
    const a = renderIntl(<PropertyStatusPanel propertyId={ID} status="onboarding" canEdit={false} />);
    expect(a.container).toBeEmptyDOMElement();
    const b = renderIntl(<PropertyStatusPanel propertyId={ID} status="terminated" canEdit />);
    expect(b.container).toBeEmptyDOMElement();
  });
});
