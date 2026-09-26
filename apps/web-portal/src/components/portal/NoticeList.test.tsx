import { screen } from "@testing-library/react";

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
});
