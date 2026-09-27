import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { EditableSection } from "./EditableSection";
import { InlineField, resetCatalogCache } from "./InlineField";
import { useAutosave } from "./useAutosave";

describe("InlineField", () => {
  it("shows the value and saves on blur once the section is in edit mode", async () => {
    const onSave = vi.fn();
    renderIntl(
      <EditableSection title="Stammdaten" canEdit>
        <InlineField name="name" label="Name" value="Haus A" onSave={onSave} />
        <InlineField name="floors" label="Geschosse" type="number" numberAs="number" value={2} onSave={onSave} />
      </EditableSection>,
    );
    expect(screen.getByText("Haus A")).toBeInTheDocument();
    expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Bearbeiten" }));
    const input = screen.getByLabelText("Name");
    await userEvent.clear(input);
    await userEvent.type(input, "Haus B");
    await userEvent.tab();
    expect(onSave).toHaveBeenCalledWith("name", "Haus B");
    const floors = screen.getByLabelText("Geschosse");
    await userEvent.clear(floors);
    await userEvent.type(floors, "3{Enter}");
    expect(onSave).toHaveBeenCalledWith("floors", 3);
    // Unchanged values are not sent again.
    await userEvent.click(input);
    await userEvent.tab();
    expect(onSave).toHaveBeenCalledTimes(2);
  });

  it("opens a single field with the pencil, cancels with Escape and sends null for empty", async () => {
    const onSave = vi.fn();
    renderIntl(
      <EditableSection title="Stammdaten" canEdit>
        <InlineField name="notes" label="Bemerkung" type="textarea" value="alt" onSave={onSave} />
      </EditableSection>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Bemerkung bearbeiten" }));
    const area = screen.getByLabelText("Bemerkung");
    expect(area).toHaveFocus();
    await userEvent.type(area, " neu{Escape}");
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText("alt")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Bemerkung bearbeiten" }));
    await userEvent.clear(screen.getByLabelText("Bemerkung"));
    await userEvent.tab();
    expect(onSave).toHaveBeenCalledWith("notes", null);
  });

  it("renders select, boolean and date values and hides the pencil without permission", async () => {
    const onSave = vi.fn();
    renderIntl(
      <div>
        <InlineField
          name="garden_use"
          label="Gartennutzung"
          type="select"
          value="partial"
          options={[
            { value: "none", label: "keine" },
            { value: "partial", label: "teilweise" },
          ]}
          onSave={onSave}
          canEdit
          editing
        />
        <InlineField name="elevator" label="Aufzug" type="boolean" value={false} onSave={onSave} canEdit editing />
        <InlineField name="managed_from" label="Verwaltet ab" type="date" value="2026-01-15" onSave={onSave} />
      </div>,
    );
    await userEvent.selectOptions(screen.getByLabelText("Gartennutzung"), "none");
    expect(onSave).toHaveBeenCalledWith("garden_use", "none");
    await userEvent.click(screen.getByRole("checkbox"));
    expect(onSave).toHaveBeenCalledWith("elevator", true);
    expect(screen.getByText("15.01.2026")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Verwaltet ab bearbeiten" })).not.toBeInTheDocument();
  });

  it("shows the validation message of the field and the states of the autosave", async () => {
    function Harness() {
      const autosave = useAutosave<{ version: number; name: string }>({ path: "buildings/b1", version: 1, debounceMs: 0 });
      return (
        <EditableSection title="Stammdaten" canEdit defaultEditing status={autosave.status} conflict={autosave.conflict}>
          <InlineField name="name" label="Name" value="Haus A" onSave={autosave.save} state={autosave.fieldState("name")} />
          <InlineField name="floors" label="Geschosse" type="number" value={2} onSave={autosave.save} state={autosave.fieldState("floors")} />
        </EditableSection>
      );
    }
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, init) => {
      const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
      if ("floors" in body) {
        return jsonResponse(
          {
            title: "Eingaben ungültig",
            status: 422,
            errors: [{ location: ["body", "floors"], field: "floors", code: "greater_than_equal", message: "Wert ist ungültig." }],
          },
          422,
        );
      }
      if (new Headers(init?.headers).get("if-match") !== "1") return jsonResponse({ title: "Konflikt", status: 412 }, 412);
      return jsonResponse({ version: 2, name: body.name }, 200, { etag: '"2"' });
    });
    renderIntl(<Harness />);
    const floors = screen.getByLabelText("Geschosse");
    await userEvent.clear(floors);
    await userEvent.type(floors, "-1");
    await act(async () => {
      await userEvent.tab();
    });
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Wert ist ungültig."));
    const name = screen.getByLabelText("Name");
    await userEvent.clear(name);
    await userEvent.type(name, "Haus B");
    await act(async () => {
      await userEvent.tab();
    });
    await waitFor(() => expect(screen.getAllByRole("status").some((el) => el.textContent === "Gespeichert")).toBe(true));
    const nameCall = fetchMock.mock.calls.find(([, init]) => String(init?.body).includes("Haus B"));
    expect(nameCall?.[0]).toBe("/api/bff/buildings/b1");
    expect(new Headers(nameCall?.[1]?.headers).get("if-match")).toBe("1");
    expect(nameCall?.[1]?.method).toBe("PATCH");
    fetchMock.mockRestore();
  });

  it("surfaces a stale version as a conflict with the reload notice", async () => {
    function Harness() {
      const autosave = useAutosave<{ version: number }>({ path: "properties/p1", version: 3, debounceMs: 0 });
      return (
        <EditableSection title="Stammdaten" canEdit defaultEditing status={autosave.status} conflict={autosave.conflict} onReload={() => undefined}>
          <InlineField name="notes" label="Bemerkung" value="" onSave={autosave.save} state={autosave.fieldState("notes")} />
        </EditableSection>
      );
    }
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ title: "Konflikt", status: 412 }, 412));
    renderIntl(<Harness />);
    await userEvent.type(screen.getByLabelText("Bemerkung"), "x{Enter}");
    await waitFor(() => expect(screen.getByRole("button", { name: "Neu laden" })).toBeInTheDocument());
    expect(screen.queryByLabelText("Bemerkung")).not.toBeInTheDocument();
    vi.restoreAllMocks();
  });

  it("retries once after a network failure", async () => {
    function Harness() {
      const autosave = useAutosave<{ version: number }>({ path: "units/u1", version: 1, debounceMs: 0 });
      return <InlineField name="label" label="Bezeichnung" value="" onSave={autosave.save} state={autosave.fieldState("label")} canEdit editing />;
    }
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(jsonResponse({ version: 2 }));
    renderIntl(<Harness />);
    await userEvent.type(screen.getByLabelText("Bezeichnung"), "EG{Enter}");
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Gespeichert"));
    expect(fetchMock).toHaveBeenCalledTimes(2);
    fetchMock.mockRestore();
  });

  it("feeds a select from a catalogue and keeps an inactive current value selectable", async () => {
    resetCatalogCache();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      expect(String(url)).toBe("/api/bff/catalogs/property_type?include_inactive=true");
      return jsonResponse([
        { code: "altbau", label: "Altbau", active: true },
        { code: "neubau", label: "Neubau", active: true },
        { code: "burg", label: "Burg", active: false },
      ]);
    });
    const onSave = vi.fn();
    renderIntl(<InlineField name="property_type_code" label="Objektart" type="select" catalog="property_type" value="burg" onSave={onSave} canEdit editing />);
    const select = await screen.findByLabelText("Objektart");
    await waitFor(() => expect(screen.getByRole("option", { name: "Burg (inaktiv)" })).toBeInTheDocument());
    expect(screen.getByRole("option", { name: "Altbau" })).toBeInTheDocument();
    expect(select).toHaveValue("burg");
    await userEvent.selectOptions(select, "neubau");
    expect(onSave).toHaveBeenCalledWith("property_type_code", "neubau");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fetchMock.mockRestore();
  });
});
