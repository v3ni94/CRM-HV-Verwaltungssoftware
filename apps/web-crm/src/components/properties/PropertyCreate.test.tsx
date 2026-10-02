import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PropertyCreate } from "./PropertyCreate";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

async function fill() {
  const inputs = screen.getAllByRole("textbox");
  await userEvent.type(inputs[0]!, "123");
  await userEvent.type(inputs[1]!, "Musterhaus");
}

describe("PropertyCreate", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    push.mockClear();
  });

  it("keeps the button disabled until number and name are valid", async () => {
    renderIntl(<PropertyCreate />);
    const submit = document.querySelector("details button") as HTMLButtonElement;
    expect(submit).toBeDisabled();
    await fill();
    expect(submit).toBeEnabled();
  });

  it("posts the body without empty fields and navigates to the new property", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: "p-9" }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<PropertyCreate />);
    await fill();
    await act(async () => {
      await userEvent.click(document.querySelector("details button") as HTMLButtonElement);
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/properties");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ number: "123", name: "Musterhaus", management_type: "hoa" });
    expect(push).toHaveBeenCalledWith("/objekte/p-9");
  });

  it("shows the error on 403 and does not navigate", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403)));
    renderIntl(<PropertyCreate />);
    await fill();
    await act(async () => {
      await userEvent.click(document.querySelector("details button") as HTMLButtonElement);
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
