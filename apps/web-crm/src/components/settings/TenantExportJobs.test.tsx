import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TenantExportJobs } from "./TenantExportJobs";

describe("TenantExportJobs", () => {
  afterEach(() => vi.restoreAllMocks());

  it("starts an export and offers the download of a finished one", async () => {
    const job = { id: "11111111-1111-1111-1111-111111111111", status: "ready", created_at: "2026-10-01T08:00:00Z", size: 2048, error: null, documents_failed: 0 };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).endsWith("/api/bff/tenant/export-jobs")) {
        return init?.method === "POST" ? jsonResponse({ ...job, status: "queued" }, 202) : jsonResponse([job]);
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<TenantExportJobs canStart />);
    const link = await screen.findByRole("link", { name: "Herunterladen" });
    expect(link).toHaveAttribute("href", `/api/bff/tenant/export-jobs/${job.id}/download`);
    await userEvent.setup().click(screen.getByRole("button", { name: "Export starten" }));
    await waitFor(() => expect(screen.getByText("Export gestartet.")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith("/api/bff/tenant/export-jobs", expect.objectContaining({ method: "POST" }));
  });

  it("shows only a hint without the tenant administrator role", () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderIntl(<TenantExportJobs canStart={false} />);
    expect(screen.queryByRole("button", { name: "Export starten" })).toBeNull();
    expect(screen.getByText(/erfordert die Rolle Mandantenadministrator/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
