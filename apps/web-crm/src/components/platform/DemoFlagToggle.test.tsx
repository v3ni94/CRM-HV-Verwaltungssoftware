import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DemoFlagToggle } from "./DemoFlagToggle";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

describe("DemoFlagToggle (AE36)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    refresh.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("marks a tenant as demo tenant after confirmation and refreshes the page", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fetchMock.mockImplementation(async () => jsonResponse({ id: "t-1", slug: "x", is_demo: true }));
    renderIntl(<DemoFlagToggle tenantId="01920000-0000-7000-8000-00000000000a" isDemo={false} />);
    await userEvent.click(screen.getByRole("button", { name: "Als Demo-Mandant kennzeichnen" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const url = fetchMock.mock.calls[0]?.[0];
    const init = fetchMock.mock.calls[0]?.[1];
    expect(String(url)).toBe("/api/bff/platform/tenants/01920000-0000-7000-8000-00000000000a/demo");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toEqual({ is_demo: true });
  });

  it("does nothing without confirmation", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderIntl(<DemoFlagToggle tenantId="01920000-0000-7000-8000-00000000000a" isDemo />);
    await userEvent.click(screen.getByRole("button", { name: "Demo-Kennzeichen entfernen" }));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the refusal of the API, for example for an open release gate", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fetchMock.mockImplementation(async () =>
      jsonResponse({ code: "MHVP-DEMO-0002", title: "Demo-Kennzeichen kann nicht gesetzt werden", status: 409 }, 409),
    );
    renderIntl(<DemoFlagToggle tenantId="01920000-0000-7000-8000-00000000000a" isDemo={false} />);
    await userEvent.click(screen.getByRole("button", { name: "Als Demo-Mandant kennzeichnen" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });
});
