import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TextBlocksAdmin } from "./TextBlocksAdmin";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));

const codes = [
  { code: "info_sheet_inspection", label: "Informationsblatt: Belegeinsicht", released: false, approved_version: null },
];
const block = {
  id: "01920000-0000-7000-8000-0000000000f1",
  code: "info_sheet_inspection",
  version: 1,
  title: "t",
  body: "Entwurfstext",
  source_note: null,
  status: "submitted" as const,
  reject_reason: null,
};

describe("TextBlocksAdmin", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the unreleased marker and offers approval only with the right", async () => {
    renderIntl(<TextBlocksAdmin codes={codes} blocks={[block]} canEdit={false} canApprove={false} />);
    expect(screen.getByText("Text nicht freigegeben")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Freigeben" })).toBeNull();
  });

  it("approves a submitted block", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ ...block, status: "approved" }));
    renderIntl(<TextBlocksAdmin codes={codes} blocks={[block]} canEdit canApprove />);
    await userEvent.click(screen.getByRole("button", { name: "Freigeben" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0]![0])).toContain(`/document-text-blocks/${block.id}/approve`);
  });
});
