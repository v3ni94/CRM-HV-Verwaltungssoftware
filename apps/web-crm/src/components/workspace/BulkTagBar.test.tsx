import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { IntlTestProvider, jsonResponse } from "@/test/intl";

import { BulkTagBar } from "./BulkTagBar";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));

function setup(checked: boolean) {
  return render(
    <IntlTestProvider>
      <form id="rows">
        <input type="checkbox" name="bulk-id" value="c1" defaultChecked={checked} aria-label="row" />
      </form>
      <BulkTagBar formId="rows" />
    </IntlTestProvider>,
  );
}

describe("BulkTagBar (GAI-615)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    refresh.mockReset();
  });

  it("keeps the buttons disabled without a tag", () => {
    setup(true);
    expect(screen.getByRole("button", { name: "Hinzufügen" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Entfernen" })).toBeDisabled();
  });

  it("reports when no row is checked and sends nothing", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    setup(false);
    await userEvent.type(screen.getByLabelText("Schlagwort für markierte"), "vip");
    await userEvent.click(screen.getByRole("button", { name: "Hinzufügen" }));
    expect(await screen.findByText("Keine Zeilen markiert.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts the checked ids with the trimmed tag and refreshes", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ changed: 1 }));
    setup(true);
    await userEvent.type(screen.getByLabelText("Schlagwort für markierte"), " vip ");
    await userEvent.click(screen.getByRole("button", { name: "Entfernen" }));
    expect(await screen.findByText("1 geändert.")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/bff/workspace/bulk");
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ action: "contacts.remove_tag", ids: ["c1"], tag: "vip" });
    expect(refresh).toHaveBeenCalled();
  });
});
