import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { LogoutButton } from "./LogoutButton";

const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));

describe("LogoutButton", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    push.mockReset();
    refresh.mockReset();
  });

  it("posts to the session logout path and returns to the sign-in page", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<LogoutButton />);
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/session/logout");
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");
    expect(push).toHaveBeenCalledWith("/anmelden");
    expect(refresh).toHaveBeenCalled();
  });
});
