import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ImmowareLearning } from "./ImmowareLearning";

const RUN = {
  id: "01920000-0000-7000-8000-0000000000r1",
  kind: "webdav",
  status: "done",
  started_at: "2026-09-27T08:00:00Z",
  finished_at: "2026-09-27T08:01:00Z",
  error: null,
};

describe("ImmowareLearning", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("opens a run with its title and returns to the list", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/api/bff/immoware/learning/runs?")) return jsonResponse({ data: [RUN], meta: { page: 1, per_page: 50, total: 1 } });
      if (url === `/api/bff/immoware/learning/runs/${RUN.id}`) {
        return jsonResponse({ ...RUN, facts: { folder_count: 2, object_number_share: 0.5, folders: [] }, diff: { first_run: true } });
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderIntl(<ImmowareLearning canStart={false} />);

    await user.click(await screen.findByRole("button", { name: "Fertig" }));
    expect(await screen.findByRole("heading", { name: "Lauf WebDAV (Dokumente)" })).toBeInTheDocument();
    expect(screen.getByText("Erster Lauf dieser Art, kein Vorlauf zum Vergleich.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Zurück zur Liste" }));
    expect(await screen.findByTestId("immoware-learning-runs")).toBeInTheDocument();
  });
});
