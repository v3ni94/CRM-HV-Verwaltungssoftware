import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ChartReleaseAdmin, type ChartTemplate } from "./ChartReleaseAdmin";

const draft: ChartTemplate = {
  id: "01920000-0000-7000-8000-00000000c001",
  code: "a1",
  name: "Anhang A.1",
  version: 1,
  released: false,
  released_at: null,
  released_by: null,
  status: "draft",
  review_requested_at: null,
  review_requested_by: null,
  release_comment: null,
  release_document_id: null,
  supersedes_id: null,
  accounts: [{ number: "001200", name: "Bank" }],
};

describe("ChartReleaseAdmin", () => {
  afterEach(() => vi.restoreAllMocks());

  it("releases a draft with a comment through the dialog and shows the history", async () => {
    const released: ChartTemplate = {
      ...draft,
      status: "released",
      released: true,
      released_at: "2026-09-27T10:00:00Z",
      released_by: "u1",
      release_comment: "Steuerberatung geprüft",
    };
    const v2: ChartTemplate = { ...draft, id: "01920000-0000-7000-8000-00000000c002", version: 2, supersedes_id: draft.id };
    let state: ChartTemplate[] = [draft];
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith(`/templates/${draft.id}/release`) && init?.method === "POST") {
        state = [released];
        return jsonResponse(released);
      }
      if (url.endsWith(`/templates/${draft.id}/versions`) && init?.method === "POST") {
        state = [released, v2];
        return jsonResponse(v2, 201);
      }
      if (url.endsWith("/accounting/templates")) return jsonResponse(state);
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<ChartReleaseAdmin initial={[draft]} canManage canApprove />);
    expect(screen.getByText("Entwurf, 1 Konten")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Freigeben" }));
    await user.type(screen.getByLabelText("Kommentar zur Freigabe"), "Steuerberatung geprüft");
    await user.click(screen.getByRole("button", { name: "Freigabe eintragen" }));
    await waitFor(() => expect(screen.getByText("Kontenrahmen freigegeben.")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/bff/accounting/templates/${draft.id}/release`,
      expect.objectContaining({ method: "POST", body: JSON.stringify({ comment: "Steuerberatung geprüft", document_id: null }) }),
    );
    expect(screen.getByText(/freigegeben am 27.09.2026/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Neue Version anlegen" }));
    await waitFor(() => expect(screen.getByText("Neue Version 2 als Entwurf angelegt.")).toBeInTheDocument());
    expect(screen.getByText("Versionsverlauf")).toBeInTheDocument();
    expect(screen.getByText("Steuerberatung geprüft")).toBeInTheDocument();
  });

  it("is read only without permissions", () => {
    renderIntl(<ChartReleaseAdmin initial={[draft]} canManage={false} canApprove={false} />);
    expect(screen.queryByRole("button", { name: "Freigeben" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "CSV" })).toHaveAttribute("href", `/api/bff/accounting/templates/${draft.id}/export?format=csv`);
  });
});
