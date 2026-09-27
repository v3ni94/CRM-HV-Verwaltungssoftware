import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { EmbeddingStatus } from "@/lib/ai";
import { jsonResponse, renderIntl } from "@/test/intl";

import { EmbeddingsStatus } from "./EmbeddingsStatus";

const STATUS: EmbeddingStatus = {
  enabled: true,
  reason: null,
  model: "text-embedding-3-small",
  documents_total: 10,
  documents_embedded: 7,
  documents_pending: 3,
  knowledge_total: 2,
  knowledge_embedded: 2,
  knowledge_pending: 0,
  chunks: 42,
  last_run_at: "2026-09-26T10:00:00Z",
  last_run_status: "succeeded",
  last_run_error: null,
  last_run_report: null,
  queued: false,
};

describe("EmbeddingsStatus", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the counters and starts an incremental or full rebuild", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).endsWith("/api/bff/ai/embeddings/reindex") && init?.method === "POST") {
        return jsonResponse({ ...STATUS, documents_pending: 0, documents_embedded: 10, queued: true }, 202);
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<EmbeddingsStatus initial={STATUS} />);
    expect(screen.getByTestId("ai-embeddings-model")).toHaveTextContent("text-embedding-3-small");
    expect(screen.getByText("7 von 10 eingebettet, 3 ausstehend")).toBeInTheDocument();
    expect(screen.getByTestId("ai-embeddings-last-run")).toHaveTextContent("erfolgreich");

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Neu aufbauen" }));
    await waitFor(() => expect(screen.getByText("Der Aufbau wurde gestartet und läuft im Hintergrund.")).toBeInTheDocument());
    expect(screen.getByText("10 von 10 eingebettet, 0 ausstehend")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bff/ai/embeddings/reindex",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ full: false }) }),
    );

    await user.click(screen.getByRole("button", { name: "Vollständig neu aufbauen" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/bff/ai/embeddings/reindex",
        expect.objectContaining({ method: "POST", body: JSON.stringify({ full: true }) }),
      ),
    );
  });

  it("disables the rebuild without a usable route and names the reason", () => {
    renderIntl(<EmbeddingsStatus initial={{ ...STATUS, enabled: false, model: null, reason: "Keine Einbettungen: Freigabe fehlt" }} />);
    expect(screen.getByTestId("ai-embeddings-model")).toHaveTextContent("Nicht aktiv");
    expect(screen.getByText("Keine Einbettungen: Freigabe fehlt")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Neu aufbauen" })).toBeDisabled();
  });

  it("shows the error when the rebuild is refused", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ title: "Ungültig", status: 422, detail: "Keine Einbettungen: Modell fehlt" }, 422),
    );
    renderIntl(<EmbeddingsStatus initial={STATUS} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Neu aufbauen" }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });
});
