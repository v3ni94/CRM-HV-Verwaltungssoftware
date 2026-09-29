import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { PhotoLightbox } from "./PhotoLightbox";

const photos = [
  { id: "a", src: "/api/portal-files/portal/handover/x/documents/a/content", title: "Küche" },
  { id: "b", src: "/api/portal-files/portal/handover/x/documents/b/content", title: "Bad" },
];

describe("PhotoLightbox", () => {
  it("shows the photo in a dialog with counter, previous and next", async () => {
    const onIndex = vi.fn();
    const onClose = vi.fn();
    renderIntl(<PhotoLightbox photos={photos} index={0} onClose={onClose} onIndex={onIndex} />);
    const dialog = screen.getByRole("dialog", { name: "Küche" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveTextContent("Foto 1 von 2");
    expect(screen.getByRole("img", { name: "Küche" })).toHaveAttribute("src", photos[0]!.src);
    expect(screen.getByRole("button", { name: "Vorheriges Foto" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Nächstes Foto" }));
    expect(onIndex).toHaveBeenCalledWith(1);
    await userEvent.keyboard("{ArrowRight}");
    expect(onIndex).toHaveBeenLastCalledWith(1);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("closes on Escape and on the close button, and never opens a new tab", async () => {
    const onClose = vi.fn();
    const { container } = renderIntl(<PhotoLightbox photos={photos} index={1} onClose={onClose} onIndex={vi.fn()} />);
    expect(container.querySelector("a[target]")).toBeNull();
    expect(screen.getByRole("button", { name: "Schließen" })).toHaveFocus();
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: "Schließen" }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
