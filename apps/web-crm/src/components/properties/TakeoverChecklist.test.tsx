import { screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { type TakeoverList, TakeoverChecklist } from "./TakeoverChecklist";

const LIST: TakeoverList = {
  property_id: "p1",
  open_count: 1,
  complete: false,
  items: [{ id: "i1", category: "insurance", label: "Versicherungen", status: "open", note: null, due_date: null }],
};

describe("TakeoverChecklist", () => {
  beforeEach(() => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(LIST));
  });
  afterEach(() => vi.restoreAllMocks());

  it("shows items with status and open count", async () => {
    renderIntl(<TakeoverChecklist propertyId="p1" canEdit />);
    await waitFor(() => expect(screen.getByTestId("takeover-items")).toBeInTheDocument());
    expect(screen.getByLabelText("Versicherungen")).toHaveValue("open");
  });

  it("is read only without edit right", async () => {
    renderIntl(<TakeoverChecklist propertyId="p1" canEdit={false} />);
    await waitFor(() => expect(screen.getByLabelText("Versicherungen")).toBeDisabled());
  });
});
