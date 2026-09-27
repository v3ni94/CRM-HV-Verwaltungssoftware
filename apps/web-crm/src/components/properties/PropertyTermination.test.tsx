import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PropertyTermination, type Termination } from "./PropertyTermination";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const PID = "0192abcd-0000-7000-8000-000000000601";
const TERMINATION: Termination = {
  id: "t1",
  terminated_by: "hoa",
  notice_date: "2026-09-01",
  effective_date: "2026-12-31",
  successor_manager_contact_id: "c9",
  successor_manager_name: "Nachfolger Verwaltung GmbH",
  successor_owner_contact_id: null,
  notice_document_id: "d1",
  notice_document_title: "Kündigung Verwaltung",
  note: "Beschluss der Versammlung",
  created_at: "2026-09-27T08:00:00Z",
};

describe("PropertyTermination", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    refresh.mockReset();
  });

  it("renders nothing for readers of an active property", () => {
    renderIntl(<PropertyTermination propertyId={PID} status="active" termination={null} canEdit={false} isSuperadmin={false} />);
    expect(screen.queryByText("Verwaltung beenden")).toBeNull();
  });

  it("requires ordered dates, confirms and posts the termination", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.startsWith("/api/bff/contacts")) return jsonResponse({ items: [{ id: "c9", display_name: "Nachfolger Verwaltung GmbH" }] });
      return jsonResponse(TERMINATION, 200);
    });
    const user = userEvent.setup();
    renderIntl(<PropertyTermination propertyId={PID} status="active" termination={null} canEdit isSuperadmin={false} />);
    await user.click(screen.getByRole("button", { name: "Verwaltung beenden" }));
    const dialog = screen.getByTestId("termination-dialog");
    const next = within(dialog).getByRole("button", { name: "Weiter" });
    expect(next).toBeDisabled();
    await user.type(within(dialog).getByLabelText("Kündigungsdatum"), "2026-09-01");
    await user.type(within(dialog).getByLabelText("Ende der Verwaltung"), "2026-08-01");
    expect(within(dialog).getByText("Das Ende der Verwaltung darf nicht vor dem Kündigungsdatum liegen.")).toBeInTheDocument();
    expect(next).toBeDisabled();
    await user.clear(within(dialog).getByLabelText("Ende der Verwaltung"));
    await user.type(within(dialog).getByLabelText("Ende der Verwaltung"), "2026-12-31");
    await user.selectOptions(within(dialog).getByLabelText("Gekündigt von"), "hoa");
    await user.type(within(dialog).getByLabelText("Nachfolgender Verwalter"), "Nach");
    await user.click(await within(dialog).findByRole("button", { name: "Nachfolger Verwaltung GmbH" }));
    await user.type(within(dialog).getByLabelText("Notiz"), "Beschluss");
    expect(next).toBeEnabled();
    await user.click(next);
    expect(within(dialog).getByText(/zum 31\.12\.2026 deaktiviert \(gekündigt von Eigentümergemeinschaft am 01\.09\.2026\)/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Verwaltung beenden" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const call = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/terminate"));
    expect(call).toBeDefined();
    const body = JSON.parse(String((call![1] as RequestInit).body));
    expect(body).toEqual({
      terminated_by: "hoa",
      notice_date: "2026-09-01",
      effective_date: "2026-12-31",
      successor_manager_contact_id: "c9",
      note: "Beschluss",
    });
  });

  it("shows the banner with successor and document links and hides reactivation from others", () => {
    renderIntl(<PropertyTermination propertyId={PID} status="terminated" termination={TERMINATION} canEdit isSuperadmin={false} />);
    const banner = screen.getByTestId("property-terminated");
    expect(within(banner).getByText("Objekt deaktiviert")).toBeInTheDocument();
    expect(within(banner).getByText("Verwaltung beendet zum 31.12.2026, gekündigt von Eigentümergemeinschaft am 01.09.2026.")).toBeInTheDocument();
    expect(within(banner).getByRole("link", { name: "Nachfolger Verwaltung GmbH" })).toHaveAttribute("href", "/kontakte/c9");
    expect(within(banner).getByRole("link", { name: "Kündigungsschreiben öffnen (Kündigung Verwaltung)" })).toHaveAttribute("href", "/dokumente/d1");
    expect(within(banner).getByText("Kein Nachfolger hinterlegt.")).toBeInTheDocument();
    expect(within(banner).queryByRole("button", { name: "Wieder aktivieren" })).toBeNull();
    expect(within(banner).getByText("Wieder aktivieren kann nur der Superadmin.")).toBeInTheDocument();
  });

  it("lets the superadmin reactivate after confirmation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ status: "active" }));
    const user = userEvent.setup();
    renderIntl(<PropertyTermination propertyId={PID} status="terminated" termination={TERMINATION} canEdit isSuperadmin />);
    await user.click(screen.getByRole("button", { name: "Wieder aktivieren" }));
    await user.click(screen.getByRole("button", { name: "Ja, wieder aktivieren" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0]![0])).toBe(`/api/bff/properties/${PID}/reactivate`);
  });
});
