import { fireEvent, screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TeamsAdmin, type TeamRow } from "./TeamsAdmin";

const U1 = "11111111-1111-7111-8111-111111111111";
const U2 = "22222222-2222-7222-8222-222222222222";
const TEAM: TeamRow = { id: "33333333-3333-7333-8333-333333333333", name: "Technik", member_user_ids: [U1] };
const MEMBERS = [
  { id: U1, label: "Anna Beispiel" },
  { id: U2, label: "Bernd Beispiel" },
];

describe("TeamsAdmin", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists teams with resolved member names and no actions for readers", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([TEAM]));
    renderIntl(<TeamsAdmin members={MEMBERS} canManage={false} />);
    const row = await screen.findByTestId("team-row");
    expect(row).toHaveTextContent("Technik");
    expect(row).toHaveTextContent("Anna Beispiel");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/teams");
  });

  it("creates a team with the chosen members", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse(TEAM, 201))
      .mockResolvedValueOnce(jsonResponse([TEAM]));
    renderIntl(<TeamsAdmin members={MEMBERS} canManage />);
    await screen.findByText("Noch keine Teams angelegt.");
    fireEvent.click(screen.getByRole("button", { name: "Team anlegen" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Technik" } });
    fireEvent.click(screen.getByLabelText("Bernd Beispiel"));
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await screen.findByTestId("team-row");
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe("/api/bff/teams");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ name: "Technik", member_user_ids: [U2] });
  });

  it("rejects an empty name without calling the API", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([]));
    renderIntl(<TeamsAdmin members={MEMBERS} canManage />);
    await screen.findByText("Noch keine Teams angelegt.");
    fireEvent.click(screen.getByRole("button", { name: "Team anlegen" }));
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte einen Namen eingeben.");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("patches name and members of an existing team", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([TEAM]))
      .mockResolvedValueOnce(jsonResponse(TEAM))
      .mockResolvedValueOnce(jsonResponse([TEAM]));
    renderIntl(<TeamsAdmin members={MEMBERS} canManage />);
    await screen.findByTestId("team-row");
    fireEvent.click(screen.getByRole("button", { name: "Team Technik bearbeiten" }));
    fireEvent.click(screen.getByLabelText("Anna Beispiel"));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Haustechnik" } });
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe(`/api/bff/teams/${TEAM.id}`);
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(String(init.body))).toEqual({ name: "Haustechnik", member_user_ids: [] });
  });

  it("shows the API refusal when the team is still in use", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([TEAM]))
      .mockResolvedValueOnce(
        jsonResponse({ title: "Konflikt", status: 409, detail: "Das Team ist Tickets oder Vorlagen zugeordnet, Löschen nicht möglich." }, 409),
      );
    renderIntl(<TeamsAdmin members={MEMBERS} canManage />);
    await screen.findByTestId("team-row");
    fireEvent.click(screen.getByRole("button", { name: "Team Technik löschen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Löschen nicht möglich");
  });
});
