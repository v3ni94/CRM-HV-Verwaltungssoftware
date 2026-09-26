import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PortalFormSubmissions } from "./PortalFormSubmissions";

const TPL = "01920000-0000-7000-8000-0000000000f1";

describe("PortalFormSubmissions", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads the submissions on demand and links account and ticket", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse([
        {
          id: "s1",
          template_id: TPL,
          account_id: "acc1",
          account_status: "active",
          contact_id: "c1",
          contact_name: "Max Mieter",
          created_at: "2026-09-26T08:30:00Z",
          unit_id: null,
          ticket_id: "t1",
          ticket_number: 4711,
          ticket_status: "new",
        },
      ]),
    );
    const user = userEvent.setup();
    renderIntl(<PortalFormSubmissions templateId={TPL} />);
    expect(fetchMock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Einreichungen anzeigen" }));
    await waitFor(() => expect(screen.getByText("Max Mieter")).toBeInTheDocument());
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`/api/bff/portal-admin/forms/${TPL}/submissions`);
    expect(screen.getByRole("link", { name: "Ticket 4711" })).toHaveAttribute("href", "/tickets/t1");
    expect(screen.getByRole("link", { name: "Max Mieter" })).toHaveAttribute("href", "/kontakte/c1");
    expect(screen.getByText("neu")).toBeInTheDocument();
    expect(screen.getByText("26.09.2026 10:30")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Einreichungen aktualisieren" })).toBeInTheDocument();
  });

  it("shows the empty state and an error from the BFF", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse({ title: "Nicht gefunden", status: 404 }, 404));
    const user = userEvent.setup();
    renderIntl(<PortalFormSubmissions templateId={TPL} />);
    await user.click(screen.getByRole("button", { name: "Einreichungen anzeigen" }));
    expect(await screen.findByText("Noch keine Einreichungen zu dieser Vorlage.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Einreichungen aktualisieren" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
