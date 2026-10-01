import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { letterBody, LetterTemplates, type LetterTemplate } from "./LetterTemplates";

const template: LetterTemplate = { id: "t1", code: "free_letter", name: "Freier Brief", subject: "{{ felder.betreff }}", body: "x", version: 1, active: true };

describe("LetterTemplates", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("builds a single letter or a serial letter body", () => {
    const a = { id: "c1", display_name: "A" };
    const b = { id: "c2", display_name: "B" };
    expect(letterBody("t1", [a], " Betreff ", "")).toEqual({ template_id: "t1", contact_id: "c1", fields: { betreff: "Betreff" } });
    expect(letterBody("t1", [a, b], "", "Text")).toEqual({ template_id: "t1", contact_ids: ["c1", "c2"], fields: { text: "Text" } });
  });

  it("creates a serial letter for two recipients and hides template management without permission", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("contacts")) return jsonResponse({ items: [{ id: "c1", display_name: "Erika" }, { id: "c2", display_name: "Max" }] });
      return jsonResponse({ documents: [{ id: "d1" }, { id: "d2" }] }, 201);
    });
    renderIntl(<LetterTemplates templates={[template]} canManage={false} />);
    expect(screen.queryByText("Vorlagen verwalten")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Empfänger suchen"), "Er");
    await user.click(await screen.findByRole("button", { name: "Erika" }));
    await user.click(screen.getByRole("button", { name: "Max" }));
    await user.click(screen.getByRole("button", { name: "Serienbrief erzeugen" }));
    await waitFor(() => expect(screen.getByText("2 Briefe erzeugt und abgelegt")).toBeInTheDocument());
    const call = fetchMock.mock.calls.find(([u]) => String(u) === "/api/bff/letters/serial");
    expect(JSON.parse(String((call?.[1] as RequestInit).body))).toEqual({ template_id: "t1", contact_ids: ["c1", "c2"], fields: {} });
  }, 20000);
});
