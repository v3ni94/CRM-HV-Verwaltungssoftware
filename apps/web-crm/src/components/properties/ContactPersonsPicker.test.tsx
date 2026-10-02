import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ContactPicker, type ContactHit, loadCatalogOptions, todayIso } from "./ContactPersonsPicker";

function Harness() {
  const [v, setV] = useState<ContactHit | null>(null);
  return <ContactPicker label="Kontakt" value={v} onChange={setV} testId="cp" />;
}

describe("ContactPersonsPicker", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("searches from two characters and picks a hit", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ items: [{ id: "c1", display_name: "Erika Beispiel" }] }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<Harness />);
    const input = screen.getByTestId("cp");
    await userEvent.type(input, "E");
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.type(input, "r");
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/contacts?q=Er&page_size=8");
    await act(async () => {
      await userEvent.click(await screen.findByRole("button", { name: "Erika Beispiel" }));
    });
    expect(screen.getByTestId("cp")).toHaveValue("Erika Beispiel");
    expect(screen.queryByTestId("cp-hits")).toBeNull();
  });

  it("shows no hits when the search is forbidden (403)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403)));
    renderIntl(<Harness />);
    await userEvent.type(screen.getByTestId("cp"), "Er");
    expect(screen.queryByTestId("cp-hits")).toBeNull();
  });

  it("loads only active catalog entries and formats today as ISO date", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse([{ code: "a", label: "A", active: true }, { code: "b", label: "B", active: false }])),
    );
    expect(await loadCatalogOptions("role")).toEqual([{ code: "a", label: "A" }]);
    expect(todayIso()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});
