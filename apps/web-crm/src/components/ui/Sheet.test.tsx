import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef, useState } from "react";

import { IntlTestProvider, renderIntl } from "@/test/intl";

import { Sheet, type SheetSize } from "./Sheet";

let pathname = "/objekte";
let search = "";
vi.mock("next/navigation", () => ({ usePathname: () => pathname, useSearchParams: () => new URLSearchParams(search) }));

function Host({ size = "md", withFooter = false, autoFocusField = false }: { size?: SheetSize; withFooter?: boolean; autoFocusField?: boolean }) {
  const [open, setOpen] = useState(false);
  const field = useRef<HTMLInputElement>(null);
  return (
    <div>
      <button type="button" onClick={() => setOpen(true)}>
        Öffnen
      </button>
      <Sheet
        open={open}
        onClose={() => setOpen(false)}
        title="Mangel bearbeiten"
        size={size}
        testId="sheet"
        initialFocusRef={autoFocusField ? field : undefined}
        footer={withFooter ? <button type="button">Speichern</button> : undefined}
      >
        <label>
          Titel
          <input ref={field} />
        </label>
        <button type="button">Zweiter</button>
      </Sheet>
    </div>
  );
}

describe("Sheet", () => {
  beforeEach(() => {
    pathname = "/objekte";
    search = "";
  });

  it("portals into body with dialog semantics, locks scroll and releases it on close", async () => {
    renderIntl(<Host />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Öffnen" }));
    const dialog = screen.getByRole("dialog", { name: "Mangel bearbeiten" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByTestId("sheet").parentElement).toBe(document.body);
    expect(screen.getByTestId("sheet")).toHaveClass("z-[90]");
    expect(document.body.style.overflow).toBe("hidden");
    await userEvent.click(within(dialog).getByRole("button", { name: "Schließen" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe("");
  });

  it("closes on Escape and on the scrim, returning focus to the opener", async () => {
    renderIntl(<Host />);
    const opener = screen.getByRole("button", { name: "Öffnen" });
    await userEvent.click(opener);
    expect(screen.getByRole("button", { name: "Schließen" })).toHaveFocus();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
    await userEvent.click(opener);
    const scrim = screen.getByTestId("sheet").firstElementChild as HTMLElement;
    expect(scrim).toHaveAttribute("aria-hidden", "true");
    await userEvent.click(scrim);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("traps Tab inside the panel and honours initialFocusRef", async () => {
    renderIntl(<Host autoFocusField />);
    await userEvent.click(screen.getByRole("button", { name: "Öffnen" }));
    const field = screen.getByLabelText("Titel");
    expect(field).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByRole("button", { name: "Zweiter" })).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByRole("button", { name: "Schließen" })).toHaveFocus();
    await userEvent.tab();
    expect(field).toHaveFocus();
    await userEvent.tab({ shift: true });
    expect(screen.getByRole("button", { name: "Schließen" })).toHaveFocus();
  });

  it("is a bottom sheet below md and a centred card from md, full covers the viewport", async () => {
    const { unmount } = renderIntl(<Host withFooter />);
    await userEvent.click(screen.getByRole("button", { name: "Öffnen" }));
    const layer = screen.getByTestId("sheet");
    expect(layer).toHaveClass("fixed", "inset-0", "items-end", "md:items-center");
    const panel = screen.getByRole("dialog");
    expect(panel).toHaveClass("rounded-t-xl", "max-h-[100dvh]", "md:max-w-lg", "md:rounded-xl");
    const footer = screen.getByRole("button", { name: "Speichern" }).parentElement as HTMLElement;
    expect(footer).toHaveClass("sticky", "bottom-0");
    expect(footer.style.paddingBottom).toContain("env(safe-area-inset-bottom)");
    unmount();
    renderIntl(<Host size="full" />);
    await userEvent.click(screen.getByRole("button", { name: "Öffnen" }));
    const full = screen.getByRole("dialog");
    expect(full).toHaveClass("h-dvh", "md:max-w-3xl");
    expect(full.style.paddingTop).toContain("env(safe-area-inset-top)");
  });

  it("closes when the route changes while open", async () => {
    const { rerender } = renderIntl(<Host />);
    await userEvent.click(screen.getByRole("button", { name: "Öffnen" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    pathname = "/kontakte";
    rerender(
      <IntlTestProvider>
        <Host />
      </IntlTestProvider>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes when only the query changes while open (review WP1)", async () => {
    const { rerender } = renderIntl(<Host />);
    await userEvent.click(screen.getByRole("button", { name: "Öffnen" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    search = "art=rental";
    rerender(
      <IntlTestProvider>
        <Host />
      </IntlTestProvider>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
