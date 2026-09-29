import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TicketTemplatesAdmin } from "./TicketTemplatesAdmin";

describe("TicketTemplatesAdmin", () => {
  afterEach(() => vi.restoreAllMocks());

  it("creates a template with a checklist item and an IBAN field", async () => {
    const created = {
      id: "tpl-1",
      category: "kaution",
      title: "Kaution einrichten",
      description: null,
      checklist: [{ key: "vertrag", label: "Vertrag geprüft", required: true }],
      extra_fields: [{ key: "iban", label: "IBAN", type: "iban", required: true }],
      default_priority: "normal",
      sla_hours: null,
      active: true,
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(created, 201));
    renderIntl(<TicketTemplatesAdmin initialTemplates={[]} canManage={true} />);

    await userEvent.click(screen.getByText("Neue Vorlage"));
    await userEvent.type(screen.getByLabelText("Kategorie"), "kaution");
    await userEvent.type(screen.getByLabelText("Titel"), "Kaution einrichten");

    await userEvent.type(screen.getByPlaceholderText("Neuer Checklistenpunkt"), "Vertrag geprüft");
    await userEvent.click(screen.getAllByText("Hinzufügen")[0]!);
    expect(screen.getByText("Vertrag geprüft")).toBeInTheDocument();

    await userEvent.type(screen.getByPlaceholderText("Neues Feld"), "IBAN");
    await userEvent.selectOptions(screen.getByDisplayValue("Text"), "iban");
    await userEvent.click(screen.getAllByText("Hinzufügen")[1]!);
    expect(screen.getByText((_, node) => node?.textContent === "IBAN (IBAN)")).toBeInTheDocument();

    await userEvent.click(screen.getByText("Speichern"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string);
    expect(body.category).toBe("kaution");
    expect(body.checklist[0]).toMatchObject({ label: "Vertrag geprüft", required: false });
    expect(body.extra_fields[0]).toMatchObject({ label: "IBAN", type: "iban" });
    expect(await screen.findByText("Kaution einrichten")).toBeInTheDocument();
  });

  it("sends the process flow fields and loads the catalogue (M19-11)", async () => {
    const created = {
      id: "tpl-3",
      category: "kaution",
      title: "Kaution",
      description: null,
      checklist: [],
      extra_fields: [],
      default_priority: "normal",
      sla_hours: null,
      active: true,
      process_code: "kaution",
      responsible_role: "accountant_no_banking",
      required_links: ["contract"],
      deadline_type_codes: ["note_follow_up"],
      document_kinds: ["Kautionsnachweis"],
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/process-catalogue/seed")) return jsonResponse({ created: 12, updated: 0, kept: 0 });
      if (url.endsWith("/tickets/templates") && !url.includes("tpl-")) return jsonResponse([created]);
      return jsonResponse(created, 201);
    });
    renderIntl(<TicketTemplatesAdmin initialTemplates={[]} canManage={true} />);

    await userEvent.click(screen.getByText("Prozesskatalog einspielen"));
    expect(await screen.findByText("Katalog eingespielt: 12 neu, 0 ergänzt, 0 unverändert.")).toBeInTheDocument();
    expect(screen.getByTestId("ticket-process-badge")).toHaveAttribute("data-process", "kaution");

    await userEvent.click(screen.getByText("Bearbeiten"));
    expect(screen.getByTestId("template-process")).toHaveValue("kaution");
    expect(screen.getByTestId("template-role")).toHaveValue("accountant_no_banking");
    expect(screen.getByLabelText("Vertrag")).toBeChecked();
    expect(screen.getByLabelText("Wiedervorlage")).toBeChecked();
    await userEvent.click(screen.getByLabelText("Einheit"));
    await userEvent.type(screen.getByPlaceholderText("Neue Unterlage"), "Kautionsabrechnung");
    await userEvent.click(screen.getAllByText("Hinzufügen").at(-1)!);
    await userEvent.click(screen.getByText("Speichern"));
    await waitFor(() => expect(fetchMock.mock.calls.some((c) => String(c[0]).endsWith("/tickets/templates/tpl-3"))).toBe(true));
    const call = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/tickets/templates/tpl-3"));
    const body = JSON.parse(call?.[1]?.body as string);
    expect(body.process_code).toBe("kaution");
    expect(body.responsible_role).toBe("accountant_no_banking");
    expect(body.required_links).toEqual(["contract", "unit"]);
    expect(body.deadline_type_codes).toEqual(["note_follow_up"]);
    expect(body.document_kinds).toEqual(["Kautionsnachweis", "Kautionsabrechnung"]);
  });

  it("hides management actions without manage permission", () => {
    renderIntl(
      <TicketTemplatesAdmin
        initialTemplates={[
          {
            id: "tpl-2",
            category: "letting",
            title: "Vermietung",
            description: null,
            checklist: [],
            extra_fields: [],
            default_priority: "normal",
            sla_hours: null,
            active: true,
          },
        ]}
        canManage={false}
      />,
    );
    expect(screen.queryByText("Bearbeiten")).not.toBeInTheDocument();
    expect(screen.queryByText("Neue Vorlage")).not.toBeInTheDocument();
  });
});
