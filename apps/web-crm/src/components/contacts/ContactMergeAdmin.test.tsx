import { fireEvent, screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ContactMergeAdmin, type ContactMerge } from "./ContactMergeAdmin";

const ROW: ContactMerge = {
  id: "m1",
  source_id: "s1",
  target_id: "t1",
  source_name: "Max Muster",
  target_name: "Maximilian Muster",
  status: "proposed",
  reason: "Dublette",
  check_result: { blockers: [], warnings: [{ code: "name_differs", detail: "Die Anzeigenamen weichen ab." }], references: { "contact_note.contact_id": 2 } },
  result: null,
  created_at: "2026-09-30T10:00:00Z",
};

describe("ContactMergeAdmin", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the check result of a proposal", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([ROW]));
    renderIntl(<ContactMergeAdmin canPropose canApprove />);
    const row = await screen.findByTestId("contact-merge-row");
    expect(row).toHaveTextContent("Max Muster");
    expect(row).toHaveTextContent("Die Anzeigenamen weichen ab.");
    expect(row).toHaveTextContent("contact_note.contact_id (2)");
  });

  it("disables execution while blockers exist and hides it without approval", async () => {
    const blocked = { ...ROW, check_result: { blockers: [{ code: "kind_differs", detail: "Person und Firma werden nicht zusammengeführt." }] } };
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([blocked]));
    const { unmount } = renderIntl(<ContactMergeAdmin canPropose={false} canApprove />);
    await screen.findByTestId("contact-merge-row");
    expect(screen.getByRole("button", { name: "Ausführen" })).toBeDisabled();
    unmount();
    renderIntl(<ContactMergeAdmin canPropose={false} canApprove={false} />);
    await screen.findByTestId("contact-merge-row");
    expect(screen.queryByRole("button", { name: "Ausführen" })).not.toBeInTheDocument();
  });

  it("executes after confirmation", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([ROW]));
    renderIntl(<ContactMergeAdmin canPropose canApprove />);
    await screen.findByTestId("contact-merge-row");
    fireEvent.click(screen.getByRole("button", { name: "Ausführen" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/contact-merges/m1/execute"))).toBe(true));
  });
});
