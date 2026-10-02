import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ContactPicker } from "./ContactPicker";

describe("ContactPicker", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("searches with kind filter and reports the picked contact", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ items: [{ id: "c1", display_name: "Erika Beispiel", extra: "x" }] }));
    vi.stubGlobal("fetch", fetchMock);
    const onPick = vi.fn();
    renderIntl(<ContactPicker label="Person" onPick={onPick} kind="person" />);
    const button = screen.getByRole("button");
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByRole("textbox"), "Eri");
    await act(async () => {
      await userEvent.click(button);
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/contacts?q=Eri&page_size=10&kind=person");
    await act(async () => {
      await userEvent.click(await screen.findByRole("button", { name: "Erika Beispiel" }));
    });
    expect(onPick).toHaveBeenCalledWith({ id: "c1", display_name: "Erika Beispiel" });
    expect(screen.queryByRole("button", { name: "Erika Beispiel" })).toBeNull();
  });

  it("shows the error on 403", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403)));
    renderIntl(<ContactPicker label="Person" onPick={vi.fn()} />);
    await userEvent.type(screen.getByRole("textbox"), "Eri{Enter}");
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
