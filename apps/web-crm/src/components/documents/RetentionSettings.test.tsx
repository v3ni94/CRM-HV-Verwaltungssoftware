import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { RetentionSettings, type RetentionProfile } from "./RetentionSettings";

const profile = {
  id: "pr1",
  document_class: "buchungsbeleg",
  legal_entity_kind: null,
  legal_basis: "Platzhalter",
  retention_years: 8,
  retention_months: 0,
  permanent: false,
  start_rule: "end_of_year_created",
  review_note: null,
  status: "entwurf",
  created_by: "u-creator",
  released_at: null,
  released_by: null,
} as RetentionProfile;

describe("RetentionSettings", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lets a second person release a draft via POST /retention-profiles/{id}/release", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ...profile, status: "freigegeben", released_by: "u-other" }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<RetentionSettings profiles={[profile]} categories={[]} userId="u-other" />);
    const release = screen.getAllByRole("button").find((b) => !(b as HTMLButtonElement).disabled && /freigeb/i.test(b.textContent ?? ""));
    expect(release).toBeDefined();
    await act(async () => {
      await userEvent.click(release!);
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/retention-profiles/pr1/release");
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");
  });

  it("does not allow the creator to release the own draft (four eyes)", () => {
    renderIntl(<RetentionSettings profiles={[profile]} categories={[]} userId="u-creator" />);
    const release = screen.getAllByRole("button").filter((b) => /freigeb/i.test(b.textContent ?? ""));
    expect(release.length).toBeGreaterThan(0);
    expect(release.every((b) => (b as HTMLButtonElement).disabled)).toBe(true);
  });

  it("shows the error when applying the profiles is refused (403)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<RetentionSettings profiles={[profile]} categories={[]} userId={null} />);
    const apply = screen.getAllByRole("button").find((b) => /anwend|zuordn/i.test(b.textContent ?? ""));
    expect(apply).toBeDefined();
    await act(async () => {
      await userEvent.click(apply!);
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/retention-profiles/apply");
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
