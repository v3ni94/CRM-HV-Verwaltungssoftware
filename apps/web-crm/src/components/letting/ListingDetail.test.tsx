import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ListingDetail, type Listing } from "./ListingDetail";

const refresh = vi.fn();
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push }) }));

const LISTING: Listing = {
  id: "0192abcd-0000-7000-8000-000000000060",
  property_id: "p1",
  unit_id: "u1",
  kind: "rental",
  status: "draft",
  title: "Schöne Wohnung",
  description: null,
  price: "850.00",
  additional_costs: null,
  deposit: null,
  available_from: "2026-11-01",
  commission_note: null,
  energy_note: null,
  living_area_sqm: "60.00",
  rooms: "2.5",
  floor: "2",
  publication_status: "not_published",
  notes: null,
};

describe("ListingDetail", () => {
  afterEach(() => vi.restoreAllMocks());

  it("activates the listing", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ ...LISTING, status: "active" }));
    renderIntl(<ListingDetail listing={LISTING} />);
    await userEvent.click(screen.getByText("Aktivieren"));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ status: "active" });
  });
});
