import { act, fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MagicLinkForm } from "./MagicLinkForm";

describe("MagicLinkForm", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("rejects an invalid e-mail address without a request", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<MagicLinkForm />);
    await userEvent.type(screen.getByRole("textbox"), "kein-at");
    await userEvent.click(screen.getByRole("button"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("requests the link and always shows the same confirmation", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<MagicLinkForm />);
    await userEvent.type(screen.getByRole("textbox"), " a@example.de ");
    await act(async () => {
      fireEvent.submit(screen.getByRole("form"));
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/session/magic-link/request");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ email: "a@example.de" });
    expect(await screen.findByTestId("magic-link-sent")).toBeInTheDocument();
  });

  it("shows the API error (429)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Too many", status: 429, detail: "x" }, 429)));
    renderIntl(<MagicLinkForm />);
    await userEvent.type(screen.getByRole("textbox"), "a@example.de");
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
