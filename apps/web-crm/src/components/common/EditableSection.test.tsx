import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { EditableSection, useEditableSection } from "./EditableSection";

function Probe() {
  const { editing, canEdit } = useEditableSection();
  return <span data-testid="probe">{`${editing}/${canEdit}`}</span>;
}

describe("EditableSection", () => {
  it("toggles the edit mode for its children with Bearbeiten and Fertig", async () => {
    const onEditingChange = vi.fn();
    renderIntl(
      <EditableSection title="Stammdaten" canEdit onEditingChange={onEditingChange}>
        <Probe />
      </EditableSection>,
    );
    expect(screen.getByTestId("probe")).toHaveTextContent("false/true");
    const toggle = screen.getByRole("button", { name: "Bearbeiten" });
    await userEvent.click(toggle);
    expect(screen.getByTestId("probe")).toHaveTextContent("true/true");
    expect(screen.getByRole("button", { name: "Fertig" })).toHaveAttribute("aria-pressed", "true");
    expect(onEditingChange).toHaveBeenLastCalledWith(true);
    await userEvent.click(screen.getByRole("button", { name: "Fertig" }));
    expect(screen.getByTestId("probe")).toHaveTextContent("false/true");
    expect(onEditingChange).toHaveBeenLastCalledWith(false);
  });

  it("hides the toggle without write permission and shows the save status", () => {
    renderIntl(
      <EditableSection title="Stammdaten" status="saved">
        <Probe />
      </EditableSection>,
    );
    expect(screen.queryByRole("button", { name: "Bearbeiten" })).not.toBeInTheDocument();
    expect(screen.getByTestId("probe")).toHaveTextContent("false/false");
    expect(screen.getByRole("status")).toHaveTextContent("Gespeichert");
  });

  it("blocks editing on a conflict and offers the reload", async () => {
    const onReload = vi.fn();
    renderIntl(
      <EditableSection title="Stammdaten" canEdit defaultEditing conflict status="conflict" onReload={onReload}>
        <Probe />
      </EditableSection>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Von jemand anderem geändert, neu laden");
    expect(screen.getByTestId("probe")).toHaveTextContent("false/false");
    expect(screen.queryByRole("button", { name: "Bearbeiten" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Neu laden" }));
    expect(onReload).toHaveBeenCalled();
  });
});
