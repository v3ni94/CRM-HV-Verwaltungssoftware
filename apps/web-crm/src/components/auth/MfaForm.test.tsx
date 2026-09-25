import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MfaForm } from "./MfaForm";

const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh, back: vi.fn() }) }));

describe("MfaForm", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    push.mockReset();
    refresh.mockReset();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("does not remember the device by default", async () => {
    fetchMock.mockImplementation(async () =>
      jsonResponse({ tenant_id: "t-1", tenants: [{ id: "t-1", name: "Mandant A" }] }),
    );
    renderIntl(<MfaForm setup={false} />);
    await userEvent.type(screen.getByLabelText("Code"), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Bestätigen" }));
    await waitFor(() => expect(push).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/session/mfa/verify");
    expect(JSON.parse(String(init?.body))).toEqual({ code: "123456", remember_device: false });
  });

  it("sends remember_device when the checkbox is ticked", async () => {
    fetchMock.mockImplementation(async () =>
      jsonResponse({ tenant_id: "t-1", tenants: [{ id: "t-1", name: "Mandant A" }] }),
    );
    renderIntl(<MfaForm setup={false} />);
    await userEvent.click(screen.getByText("Auf diesem Gerät 180 Tage merken"));
    await userEvent.type(screen.getByLabelText("Code"), "654321");
    await userEvent.click(screen.getByRole("button", { name: "Bestätigen" }));
    await waitFor(() => expect(push).toHaveBeenCalled());
    const [, init] = fetchMock.mock.calls[0]!;
    expect(JSON.parse(String(init?.body))).toEqual({ code: "654321", remember_device: true });
  });

  it("shows an error for an invalid code and never calls the API", async () => {
    renderIntl(<MfaForm setup={false} />);
    await userEvent.type(screen.getByLabelText("Code"), "12");
    await userEvent.click(screen.getByRole("button", { name: "Bestätigen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Der Code besteht aus 6 bis 8 Ziffern.");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
