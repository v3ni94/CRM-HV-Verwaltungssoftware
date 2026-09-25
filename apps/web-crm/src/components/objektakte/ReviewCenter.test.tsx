import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ReviewCenter, type CategoryOption, type ReviewCase } from "./ReviewCenter";

const category: CategoryOption = { id: "cat-1", code: "05", name: "Eigentümerakte" };

const openCase: ReviewCase = {
  id: "case-1",
  document_id: "doc-1",
  document_title: "Forderungsaufstellung",
  document_preview_url: "/api/v1/documents/doc-1/content",
  stage: "rules",
  candidates: { candidates: [{ category_id: "cat-1", document_type: "forderungsaufstellung", score: 0.9 }] },
  proposed_action: null,
  priority: 100,
  status: "open",
  snoozed_until: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("ReviewCenter", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lists a case, shows its candidate and accepts it", async () => {
    const fetchMock = vi
      .fn()
      // initial list load (status=open effect)
      .mockResolvedValueOnce(jsonResponse({ items: [openCase] }))
      // decide (accept_candidate)
      .mockResolvedValueOnce(jsonResponse({ case: { ...openCase, status: "resolved" } }))
      // reload after decide
      .mockResolvedValueOnce(jsonResponse({ items: [{ ...openCase, status: "resolved" }] }));
    vi.stubGlobal("fetch", fetchMock);

    renderIntl(<ReviewCenter categories={[category]} />);

    expect(await screen.findByText("Forderungsaufstellung")).toBeInTheDocument();

    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Details" }));
    });
    expect(screen.getAllByText(/Eigentümerakte/).length).toBeGreaterThan(0);

    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Übernehmen" }));
    });

    const decideCall = fetchMock.mock.calls.find(([url]) => String(url).includes("/decide"));
    expect(decideCall).toBeDefined();
    const body = JSON.parse(String(decideCall?.[1]?.body));
    expect(body).toEqual({ action: "accept_candidate", candidate_index: 0 });
  });

  it("bulk decides selected cases with the chosen category", async () => {
    const second: ReviewCase = { ...openCase, id: "case-2", document_title: "Zweites Dokument" };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ items: [openCase, second] }))
      .mockResolvedValueOnce(jsonResponse({ decided: ["case-1", "case-2"], skipped: [] }))
      .mockResolvedValueOnce(jsonResponse({ items: [] }));
    vi.stubGlobal("fetch", fetchMock);

    renderIntl(<ReviewCenter categories={[category]} />);

    await screen.findByText("Forderungsaufstellung");
    const checkboxes = screen.getAllByRole("checkbox", { name: "Auswählen" });

    await act(async () => {
      await userEvent.click(checkboxes[0]!);
      await userEvent.click(checkboxes[1]!);
      await userEvent.selectOptions(screen.getByLabelText("Sammel-Zielkategorie"), "cat-1");
      await userEvent.click(screen.getByRole("button", { name: /Sammelentscheidung/ }));
    });

    const bulkCall = fetchMock.mock.calls.find(([url]) => String(url).includes("bulk-decide"));
    expect(bulkCall).toBeDefined();
    const body = JSON.parse(String(bulkCall?.[1]?.body));
    expect(body.case_ids).toEqual(["case-1", "case-2"]);
    expect(body.category_id).toBe("cat-1");
  });
});
