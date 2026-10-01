import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TakeoverTicketDefaultsCard } from "./TakeoverTicketDefaultsCard";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const teams = [{ id: "t-1", label: "Objektbetreuung" }];
const members = [{ id: "u-1", label: "Anna Admin" }];

afterEach(() => vi.restoreAllMocks());

describe("TakeoverTicketDefaultsCard", () => {
  it("saves the chosen team and assignee via PUT", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ team_id: "t-1", assignee_user_id: "u-1" }),
    );
    renderIntl(
      <TakeoverTicketDefaultsCard
        defaults={{ team_id: null, assignee_user_id: null }}
        teams={teams}
        members={members}
        canManage
        incomplete={false}
      />,
    );
    await userEvent.selectOptions(screen.getByLabelText("Standardteam"), "t-1");
    await userEvent.selectOptions(screen.getByLabelText("Zuständiger"), "u-1");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/bff/onboarding/takeover-ticket-defaults");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toEqual({ team_id: "t-1", assignee_user_id: "u-1" });
    expect(await screen.findByRole("status")).toHaveTextContent("Gespeichert.");
  });

  it("sends null for the empty choice and keeps an unknown stored value selectable", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}));
    renderIntl(
      <TakeoverTicketDefaultsCard
        defaults={{ team_id: "t-9", assignee_user_id: "u-1" }}
        teams={[]}
        members={members}
        canManage
        incomplete
      />,
    );
    expect(screen.getByLabelText("Standardteam")).toHaveValue("t-9");
    await userEvent.selectOptions(screen.getByLabelText("Zuständiger"), "");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(JSON.parse(String(fetchMock.mock.calls[0]![1]?.body))).toEqual({
      team_id: "t-9",
      assignee_user_id: null,
    });
  });

  it("is read only without update permission", () => {
    renderIntl(
      <TakeoverTicketDefaultsCard
        defaults={{ team_id: null, assignee_user_id: null }}
        teams={teams}
        members={members}
        canManage={false}
        incomplete={false}
      />,
    );
    expect(screen.queryByRole("button", { name: "Speichern" })).toBeNull();
    expect(screen.getByLabelText("Standardteam")).toBeDisabled();
  });

  it("shows the backend error", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ title: "Team unbekannt", status: 422 }, 422),
    );
    renderIntl(
      <TakeoverTicketDefaultsCard
        defaults={{ team_id: null, assignee_user_id: null }}
        teams={teams}
        members={members}
        canManage
        incomplete={false}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
