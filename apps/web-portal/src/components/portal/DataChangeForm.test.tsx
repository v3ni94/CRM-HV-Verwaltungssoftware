import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DataChangeForm } from "./DataChangeForm";

describe("DataChangeForm (address, M21-02)", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("requires the date from which the address applies", async () => {
    const user = userEvent.setup();
    renderIntl(<DataChangeForm />);
    await user.type(screen.getByLabelText("Straße"), "Neue Straße");
    await user.type(screen.getByLabelText("PLZ"), "40213");
    await user.type(screen.getByLabelText("Ort"), "Düsseldorf");
    await user.click(screen.getByRole("button", { name: "Änderung vorschlagen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("ab dem die Anschrift gilt");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("uploads the evidence first and submits the address with valid_from and document_id", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ id: "d1" }, 201)).mockResolvedValueOnce(jsonResponse({ id: "cr1" }, 201));
    renderIntl(<DataChangeForm />);
    await user.type(screen.getByLabelText("Straße"), "Neue Straße");
    await user.type(screen.getByLabelText("Hausnummer"), "5");
    await user.type(screen.getByLabelText("PLZ"), "40213");
    await user.type(screen.getByLabelText("Ort"), "Düsseldorf");
    await user.type(screen.getByLabelText("Gültig ab"), "2026-10-01");
    await user.upload(
      screen.getByLabelText(/Nachweis anhängen/),
      new File(["%PDF"], "melde.pdf", { type: "application/pdf" }),
    );
    await user.click(screen.getByRole("button", { name: "Änderung vorschlagen" }));
    await waitFor(() => expect(screen.getByText("Die Änderung wurde als Vorschlag übermittelt.")).toBeInTheDocument());
    const calls = vi.mocked(fetch).mock.calls.map(([url, init]) => [String(url), init ?? {}] as const);
    expect(calls[0]?.[0]).toBe("/api/bff/portal/uploads");
    expect(calls[0]?.[1].body).toBeInstanceOf(FormData);
    expect(calls[1]?.[0]).toBe("/api/bff/portal/change-requests");
    expect(JSON.parse(String(calls[1]?.[1].body))).toEqual({
      kind: "address",
      payload: {
        street: "Neue Straße",
        house_number: "5",
        postal_code: "40213",
        city: "Düsseldorf",
        valid_from: "2026-10-01",
        document_id: "d1",
      },
    });
  });
});
