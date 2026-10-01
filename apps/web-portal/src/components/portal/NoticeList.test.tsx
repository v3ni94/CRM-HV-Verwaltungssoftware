import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { NoticeList, type PortalNotice } from "./NoticeList";

function notice(overrides: Partial<PortalNotice> = {}): PortalNotice {
  return {
    id: "01920000-0000-7000-8000-000000000001",
    property_id: "p1",
    property_number: "821",
    property_name: "Aushang-WEG",
    title: "Wasser wird abgestellt",
    body: "Am Dienstag von 9 bis 12 Uhr.",
    valid_from: "2026-09-20",
    valid_to: "2026-10-05",
    has_document: false,
    is_new: false,
    created_at: "2026-09-20T08:00:00Z",
    ...overrides,
  };
}

describe("NoticeList", () => {
  it("shows the empty state", () => {
    renderIntl(<NoticeList notices={[]} />);
    expect(screen.getByText("Derzeit keine Aushänge.")).toBeInTheDocument();
  });

  it("renders title, text, property, validity, new badge and attachment link", () => {
    renderIntl(
      <NoticeList
        notices={[
          notice({ is_new: true, has_document: true }),
          notice({ id: "01920000-0000-7000-8000-000000000002", title: "Hausordnung", body: "Gilt ab sofort.", valid_to: null }),
        ]}
      />,
    );
    expect(screen.getByText("Wasser wird abgestellt")).toBeInTheDocument();
    expect(screen.getByText("Am Dienstag von 9 bis 12 Uhr.")).toBeInTheDocument();
    expect(screen.getAllByText(/821 Aushang-WEG/)).toHaveLength(2);
    expect(screen.getByText(/Gültig bis 05\.10\.2026/)).toBeInTheDocument();
    expect(screen.getByText(/Seit 20\.09\.2026/)).toBeInTheDocument();
    expect(screen.getAllByText("Neu")).toHaveLength(1);
    const link = screen.getByRole("link", { name: "Anlage herunterladen" });
    expect(link).toHaveAttribute("href", "/api/portal-files/portal/notices/01920000-0000-7000-8000-000000000001/document");
  });

  it("shows the level, several attachments and confirms the reading once", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response("{}", { status: 200, headers: { "content-type": "application/json" } })));
    vi.stubGlobal("fetch", fetchMock);
    const id = "01920000-0000-7000-8000-000000000009";
    renderIntl(
      <NoticeList
        notices={[
          notice({
            id,
            type: "danger",
            has_document: true,
            documents: [
              { id: "d1", filename: "Plan.pdf" },
              { id: "d2", filename: "Skizze.pdf" },
            ],
            read: false,
          }),
        ]}
      />,
    );
    expect(screen.getByText("Gefahr")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Anlage herunterladen: Plan.pdf" })).toHaveAttribute("href", `/api/portal-files/portal/notices/${id}/documents/d1`);
    expect(screen.getByRole("link", { name: "Anlage herunterladen: Skizze.pdf" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Als gelesen bestätigen" }));
    await waitFor(() => expect(screen.getByText(/Als gelesen bestätigt/)).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(`/api/bff/portal/notices/${id}/read`, expect.objectContaining({ method: "POST" }));
    expect(screen.queryByRole("button", { name: "Als gelesen bestätigen" })).toBeNull();
    vi.unstubAllGlobals();
  });
});
