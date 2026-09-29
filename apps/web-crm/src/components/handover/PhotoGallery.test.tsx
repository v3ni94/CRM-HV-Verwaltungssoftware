import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { PhotoGallery } from "./PhotoGallery";
import type { Doc } from "./types";

vi.mock("next/navigation", () => ({
  usePathname: () => "/makler/uebergabe/1",
  useSearchParams: () => new URLSearchParams(),
}));

const docs: Doc[] = [1, 2, 3].map((n) => ({
  id: `0192abcd-0000-7000-8000-00000000000${n}`,
  title: `Foto ${n}`,
  filename: `foto${n}.jpg`,
  mime_type: "image/jpeg",
  size: 1000,
  kind: "photo",
  section: "defect",
  item_id: "x",
  created_at: "2026-09-25T10:00:00Z",
}));

describe("PhotoGallery", () => {
  it("shows the counter, moves with the buttons and the arrow keys, closes on Escape and locks the body scroll", async () => {
    const onClose = vi.fn();
    renderIntl(<PhotoGallery open onClose={onClose} docs={docs} index={1} itemTitle="Kratzer" />);
    expect(screen.getByTestId("gallery-counter")).toHaveTextContent("2 von 3");
    expect(screen.getByTestId("gallery-image")).toHaveAttribute("src", `/api/handover-files/documents/${docs[1]!.id}/content`);
    expect(document.body.style.overflow).toBe("hidden");
    await userEvent.click(screen.getByLabelText("Nächstes Foto"));
    expect(screen.getByTestId("gallery-counter")).toHaveTextContent("3 von 3");
    await userEvent.click(screen.getByLabelText("Nächstes Foto"));
    expect(screen.getByTestId("gallery-counter")).toHaveTextContent("1 von 3");
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(screen.getByTestId("gallery-counter")).toHaveTextContent("3 von 3");
    expect(screen.getByText(/Kratzer/)).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("swipes between photos with pointer events", () => {
    renderIntl(<PhotoGallery open onClose={() => undefined} docs={docs} index={0} />);
    const stage = screen.getByTestId("gallery-stage");
    fireEvent.pointerDown(stage, { clientX: 200, clientY: 100 });
    fireEvent.pointerUp(stage, { clientX: 80, clientY: 105 });
    expect(screen.getByTestId("gallery-counter")).toHaveTextContent("2 von 3");
  });
});
