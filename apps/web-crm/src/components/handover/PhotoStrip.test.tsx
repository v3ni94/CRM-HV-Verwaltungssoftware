import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { PhotoStrip } from "./PhotoStrip";
import type { Doc } from "./types";

vi.mock("next/navigation", () => ({
  usePathname: () => "/makler/uebergabe/1",
  useSearchParams: () => new URLSearchParams(),
}));

const P = "0192abcd-0000-7000-8000-000000000060";
const docs: Doc[] = [
  {
    id: "0192abcd-0000-7000-8000-000000000001",
    title: "Kratzer",
    filename: "k.jpg",
    mime_type: "image/jpeg",
    size: 10,
    kind: "photo",
    section: "defect",
    item_id: "x",
    created_at: "2026-09-25T10:00:00Z",
    thumbnail_url: `/api/v1/handover/protocols/${P}/documents/0192abcd-0000-7000-8000-000000000001/thumbnail`,
  },
];

describe("PhotoStrip", () => {
  it("renders 96 px tiles from the thumbnail path and opens the gallery on tap", async () => {
    renderIntl(<PhotoStrip docs={docs} itemTitle="Mangel" />);
    const img = screen.getByRole("img", { name: "Kratzer" });
    expect(img.className).toContain("h-24");
    expect(img).toHaveAttribute("src", `/api/handover-files/handover/protocols/${P}/documents/0192abcd-0000-7000-8000-000000000001/thumbnail`);
    expect(img).toHaveAttribute("loading", "lazy");
    await userEvent.click(screen.getByLabelText("Foto öffnen: Kratzer"));
    expect(screen.getByTestId("photo-gallery")).toBeInTheDocument();
    expect(screen.getByText("1 von 1")).toBeInTheDocument();
  });

  it("removes only after the confirmation with the deletion text", async () => {
    const onRemove = vi.fn(async () => undefined);
    renderIntl(<PhotoStrip docs={docs} onRemove={onRemove} />);
    await userEvent.click(screen.getByLabelText("Foto entfernen: Kratzer"));
    expect(screen.getByText(/Ist das Foto in keiner anderen Fassung verknüpft, wird die Datei endgültig gelöscht/)).toBeInTheDocument();
    await userEvent.click(screen.getByText("Abbrechen"));
    expect(onRemove).not.toHaveBeenCalled();
    await userEvent.click(screen.getByLabelText("Foto entfernen: Kratzer"));
    await userEvent.click(screen.getByTestId("confirm-sheet-confirm"));
    await waitFor(() => expect(onRemove).toHaveBeenCalledWith(docs[0]));
  });

  it("shows no remove button without a handler (locked protocol)", () => {
    renderIntl(<PhotoStrip docs={docs} />);
    expect(screen.queryByLabelText("Foto entfernen: Kratzer")).not.toBeInTheDocument();
  });
});
