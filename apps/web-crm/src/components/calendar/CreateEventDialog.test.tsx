import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { CreateEventDialog } from "./CreateEventDialog";

/** M31 WP3: the create dialog is a Sheet with the submit button in the sticky footer. */
describe("CreateEventDialog as a sheet", () => {
  it("renders a dialog with the submit in the footer and a stacked recurrence grid", async () => {
    const onCreate = vi.fn().mockResolvedValue(null);
    const onClose = vi.fn();
    renderIntl(<CreateEventDialog defaultTarget="internal" hasOwnMailbox={false} hasDefaultMailbox={false} onCreate={onCreate} onClose={onClose} />);
    const dialog = screen.getByRole("dialog", { name: "Termin anlegen" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    const submit = within(dialog).getByRole("button", { name: "Termin anlegen" });
    // The footer is outside the form; the button targets it by id.
    expect(submit.closest("form")).toBeNull();
    expect(submit).toHaveAttribute("form");
    const form = dialog.querySelector("form")!;
    expect(form.id).toBe(submit.getAttribute("form"));
    expect(screen.getByLabelText("Titel")).toHaveFocus();
    await userEvent.type(within(dialog).getByLabelText("Titel"), "Begehung");
    await userEvent.type(within(dialog).getByLabelText("Datum"), "2026-10-01");
    const grid = within(dialog).getByLabelText("Wiederholung").closest(".grid")!;
    expect(grid.className).toContain("grid-cols-1");
    expect(grid.className).toContain("sm:grid-cols-3");
    await userEvent.click(submit);
    expect(onCreate).toHaveBeenCalledWith(expect.objectContaining({ title: "Begehung", starts_on: "2026-10-01", target: "internal" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("closes on the cancel button and on Escape", async () => {
    const onClose = vi.fn();
    renderIntl(<CreateEventDialog defaultTarget="internal" hasOwnMailbox={false} hasDefaultMailbox={false} onCreate={vi.fn()} onClose={onClose} />);
    await userEvent.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
