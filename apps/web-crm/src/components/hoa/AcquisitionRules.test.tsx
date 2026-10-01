import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AcquisitionRules } from "./AcquisitionRules";

const payload = {
  items: [{ acquisition_kind: "gift", kind_label: "Schenkung", variant: "manual_release", is_default: true, source_note: null }],
  variants: [
    { code: "manual_release", label: "Manuelle Freigabe" },
    { code: "by_due_date", label: "Zuordnung nach Fälligkeit" },
  ],
  note: "Konfiguration zur fachlichen Prüfung",
};

describe("AcquisitionRules", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the default and saves a changed variant", async () => {
    const calls: { url: string; method: string; body: unknown }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const method = init?.method ?? "GET";
      calls.push({ url: String(input), method, body: init?.body ? JSON.parse(String(init.body)) : null });
      if (method === "PUT") return jsonResponse({ ...payload.items[0], variant: "by_due_date", is_default: false });
      return jsonResponse(payload);
    });
    renderIntl(<AcquisitionRules />);
    await waitFor(() => expect(screen.getByText("Schenkung")).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText("Variante Schenkung"), "by_due_date");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(screen.getByText("Regel gespeichert")).toBeInTheDocument());
    expect(calls[1]).toEqual({ url: "/api/bff/hoa/acquisition-rules/gift", method: "PUT", body: { variant: "by_due_date", source_note: null } });
  });
});
