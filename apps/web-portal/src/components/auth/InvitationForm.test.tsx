import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { InvitationForm } from "./InvitationForm";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn(), back: vi.fn() }) }));

const PW = "ein-langes-passwort";

async function fill(code: string, pw = PW, repeat = PW) {
  const codeBox = screen.getByLabelText("Einladungscode");
  await userEvent.clear(codeBox);
  if (code) await userEvent.type(codeBox, code);
  await userEvent.type(screen.getByLabelText("Neues Passwort"), pw);
  await userEvent.type(screen.getByLabelText("Passwort wiederholen"), repeat);
  await act(async () => {
    await userEvent.click(screen.getByRole("button", { name: "Zugang aktivieren" }));
  });
}

describe("InvitationForm", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    push.mockClear();
  });

  it.each([
    ["kurz", PW, PW, "Einladungscode"],
    ["abcdefghijkl", "kurz", "kurz", "mindestens 12 Zeichen"],
    ["abcdefghijkl", PW, "anderes-passwort-1", "stimmen nicht überein"],
  ])("validates %s before any request", async (code, pw, repeat, message) => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<InvitationForm />);
    await fill(code, pw, repeat);
    expect(screen.getByRole("alert")).toHaveTextContent(message);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts the trimmed code and password, then offers the login", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: "active" }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<InvitationForm code="  abcdefghijkl  " />);
    await userEvent.type(screen.getByLabelText("Neues Passwort"), PW);
    await userEvent.type(screen.getByLabelText("Passwort wiederholen"), PW);
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Zugang aktivieren" }));
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/session/invitation");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ token: "abcdefghijkl", password: PW });
    expect(await screen.findByRole("status")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Zur Anmeldung" }));
    expect(push).toHaveBeenCalledWith("/anmelden");
  });

  it("shows the server error and stays on the form", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403)));
    renderIntl(<InvitationForm code="abcdefghijkl" />);
    await userEvent.type(screen.getByLabelText("Neues Passwort"), PW);
    await userEvent.type(screen.getByLabelText("Passwort wiederholen"), PW);
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Zugang aktivieren" }));
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("status")).toBeNull();
  });
});
