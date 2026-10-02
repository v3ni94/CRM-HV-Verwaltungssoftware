import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { FastTableImportSwitch } from "./FastTableImportSwitch";

describe("FastTableImportSwitch (GAI-615)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads the state, is locked until loaded and saves with PUT", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ enabled: false }))
      .mockResolvedValueOnce(jsonResponse({ enabled: true }));
    renderIntl(<FastTableImportSwitch />);
    const box = screen.getByRole("checkbox", { name: "Schneller Tabellenimport" });
    expect(box).toBeDisabled();
    await vi.waitFor(() => expect(box).toBeEnabled());
    expect(box).not.toBeChecked();
    await userEvent.click(box);
    await vi.waitFor(() => expect(box).toBeChecked());
    const [, init] = fetchMock.mock.calls[1]!;
    expect((init as RequestInit).method).toBe("PUT");
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ enabled: true });
  });

  it("shows the refusal and keeps the old state", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ enabled: false }))
      .mockResolvedValueOnce(jsonResponse({ title: "Keine Berechtigung", status: 403 }, 403));
    renderIntl(<FastTableImportSwitch />);
    const box = screen.getByRole("checkbox");
    await vi.waitFor(() => expect(box).toBeEnabled());
    await userEvent.click(box);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(box).not.toBeChecked();
  });
});
