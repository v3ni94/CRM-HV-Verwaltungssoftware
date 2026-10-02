import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ImportRoleForm } from "./ImportRoleForm";

describe("ImportRoleForm", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("applies the selected role to the import run and reports the count", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ import_run_id: "r1", role: "mieter", contacts_changed: 4 }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<ImportRoleForm id="r1" />);
    await userEvent.selectOptions(screen.getByRole("combobox"), "mieter");
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/ai/import-runs/r1/apply-role");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ role: "mieter" });
    expect(await screen.findByText(/4/)).toBeInTheDocument();
  });

  it("shows an error for a forbidden request (403)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "verboten" }, 403)));
    renderIntl(<ImportRoleForm id="r1" />);
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
