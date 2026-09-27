import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PostalOutbox, type PostalJob } from "./PostalOutbox";

const job: PostalJob = {
  id: "11111111-1111-1111-1111-111111111111",
  dispatch_id: "22222222-2222-2222-2222-222222222222",
  document_id: "33333333-3333-3333-3333-333333333333",
  contact_id: "44444444-4444-4444-4444-444444444444",
  dunning_case_id: "55555555-5555-5555-5555-555555555555",
  provider: "letterxpress",
  provider_job_id: "6035143",
  status: "sent",
  options: { registered: "r1", color: false, duplex: true },
  recipient_address: "Knopf, Jim\nBahnhofstr. 1\n21337 Lüneburg",
  filename: "Mahnung.pdf",
  pages: 2,
  price: "1.51",
  tracking_code: "RC123456789DE",
  tracking_status: null,
  error: null,
  submitted_at: "2026-09-27T10:00:00Z",
  last_polled_at: null,
  completed_at: null,
  created_at: "2026-09-27T10:00:00Z",
};

describe("PostalOutbox", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists jobs with provider status and records a manual delivery with evidence", async () => {
    const calls: { url: string; method: string; body: unknown }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null });
      if (url.startsWith("/api/bff/postal/jobs?") && method === "GET") return jsonResponse([job], 200);
      if (url === `/api/bff/postal/jobs/${job.id}` && method === "GET") {
        return jsonResponse({ ...job, events: [{ id: "e1", status: "sent", source: "provider", detail: "done", occurred_at: job.created_at }] }, 200);
      }
      if (url === `/api/bff/postal/jobs/${job.id}/manual` && method === "POST") {
        return jsonResponse({ ...job, status: "delivered", completed_at: "2026-09-27T12:00:00Z" }, 200);
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });

    renderIntl(<PostalOutbox canWrite canSettings={false} />);

    expect(await screen.findByText(/Bahnhofstr\. 1/)).toBeInTheDocument();
    expect(screen.getAllByText("Versendet").length).toBeGreaterThan(0);
    expect(screen.getByText("RC123456789DE")).toBeInTheDocument();
    expect(screen.getByText("Mahnschreiben")).toBeInTheDocument();
    expect(screen.getByText("Einschreiben Einwurf")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Details" }));
    expect(await screen.findByText(/done/)).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Neuer Status"), "delivered");
    await userEvent.selectOptions(screen.getByLabelText("Nachweisart"), "registered_mail");
    await userEvent.type(screen.getByLabelText(/Nachweis \(/), "RC123456789DE");
    await userEvent.click(screen.getByRole("button", { name: "Erfassen" }));

    await waitFor(() => {
      const manual = calls.find((c) => c.url.endsWith("/manual"));
      expect(manual?.body).toMatchObject({ status: "delivered", evidence_kind: "registered_mail", evidence_ref: "RC123456789DE" });
    });
    await waitFor(() => expect(screen.getAllByText("Zugestellt").length).toBeGreaterThan(1));
  });

  it("shows the empty state and the settings panel for administrators", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.startsWith("/api/bff/postal/jobs?")) return jsonResponse([], 200);
      if (url === "/api/bff/postal/settings") {
        return jsonResponse(
          { provider: "manual", enabled: false, username: null, has_api_key: false, mode: "test", default_color: false, default_duplex: true, default_registered: null, last_balance: null, last_checked_at: null, last_error: null, providers: ["manual", "letterxpress"] },
          200,
        );
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });

    renderIntl(<PostalOutbox canWrite canSettings />);

    expect(await screen.findByText("Keine Postaufträge.")).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Postdienst einrichten" }));
    expect(await screen.findByLabelText("Postdienst")).toHaveValue("manual");
    // Credentials and the release switch only appear for an external provider.
    expect(screen.queryByLabelText("Versand über den Anbieter freigegeben")).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Postdienst"), "letterxpress");
    expect(screen.getByLabelText("Versand über den Anbieter freigegeben")).not.toBeChecked();
    expect(screen.getByLabelText("API-Schlüssel")).toBeInTheDocument();
  });
});
