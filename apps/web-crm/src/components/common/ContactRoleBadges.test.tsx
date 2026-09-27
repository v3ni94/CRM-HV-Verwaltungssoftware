import { screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ContactRoleBadges } from "./ContactRoleBadges";

const CONTACT = "0192abcd-0000-7000-8000-000000000001";
const PROP = "0192abcd-0000-7000-8000-000000000020";
const UNIT = "0192abcd-0000-7000-8000-000000000030";

describe("ContactRoleBadges", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders nothing while relations are still loading or empty", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([]));
    const { container } = renderIntl(<ContactRoleBadges contactId={CONTACT} />);
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it("shows Mieter and Beirat with links to unit and property, several roles at once", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      expect(String(input)).toBe(`/api/bff/contacts/${CONTACT}/relations`);
      return jsonResponse([
        {
          kind: "mieter",
          property_id: PROP,
          property_name: "812 Musterhaus",
          unit_id: UNIT,
          unit_label: "12",
          active: true,
          category_code: null,
        },
        {
          kind: "kontakt",
          property_id: PROP,
          property_name: "812 Musterhaus",
          unit_id: null,
          unit_label: null,
          active: true,
          category_code: "board",
        },
        {
          kind: "eigentuemer",
          property_id: PROP,
          property_name: "812 Musterhaus",
          unit_id: null,
          unit_label: null,
          active: false,
          category_code: null,
        },
      ]);
    });
    renderIntl(<ContactRoleBadges contactId={CONTACT} />);
    const badges = await screen.findByTestId("contact-role-badges");
    expect(badges).toHaveTextContent("Mieter");
    expect(badges).toHaveTextContent("Beirat");
    // The inactive Eigentümer relation is not shown.
    expect(badges).not.toHaveTextContent("Eigentümer");
    const unitLink = screen.getByRole("link", { name: "12" });
    expect(unitLink).toHaveAttribute("href", "/vermietung/einheit/" + UNIT);
    expect(screen.getAllByRole("link", { name: "812 Musterhaus" }).length).toBeGreaterThan(0);
  });
});
