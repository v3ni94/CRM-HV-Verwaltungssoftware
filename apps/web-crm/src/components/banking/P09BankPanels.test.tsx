import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AiPostingPanel, AiPostingSwitch } from "./AiPostingPanel";
import { AutoPostingDigests } from "./AutoPostingDigests";
import { BankSyncSettingsCard } from "./BankSyncSettingsCard";
import { PayerIbanButton } from "./PayerIbanButton";

const TX = "0192abcd-0000-7000-8000-000000000001";

afterEach(() => vi.restoreAllMocks());

describe("AiPostingPanel (M12-04)", () => {
  it("shows model, cost, account, reasoning and confidence of an AI proposal", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({
        bank_transaction_id: TX,
        note: "",
        proposals: [
          {
            id: "p1",
            decision: "pending",
            created_at: "2026-09-30T08:00:00Z",
            proposed: { account_number: "4200", splits: [], reasoning: "Wiederkehrende Wartung", confidence: 0.72, warnings: [] },
            run: { provider: "anthropic", model: "claude-x", prompt_version: "v1", status: "succeeded", cost_eur: "0.0123", tokens_in: 1, tokens_out: 1 },
          },
        ],
      }),
    );
    renderIntl(<AiPostingPanel txId={TX} canRequest />);
    expect(await screen.findByText(/claude-x/)).toBeInTheDocument();
    expect(screen.getByText(/4200/)).toBeInTheDocument();
    expect(screen.getByText(/Wiederkehrende Wartung/)).toBeInTheDocument();
    expect(screen.getByText(/72/)).toBeInTheDocument();
  });

  it("shows the refusal reason when the tenant switch or provider release is missing", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) =>
      (init?.method ?? "GET") === "POST"
        ? jsonResponse({ type: "about:blank", title: "KI-Kontierung nicht freigegeben", status: 409, detail: "Schalter aus" }, 409)
        : jsonResponse({ bank_transaction_id: TX, proposals: [], note: "" }),
    );
    renderIntl(<AiPostingPanel txId={TX} canRequest />);
    await userEvent.click(await screen.findByRole("button", { name: "KI-Vorschlag anfordern" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("toggles the tenant switch and shows the blocked reason", async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      calls.push(init?.method ?? "GET");
      return jsonResponse({ enabled: (init?.method ?? "GET") === "PUT", blocked_reason: "Kein Anbieter mit AVV freigegeben" });
    });
    renderIntl(<AiPostingSwitch />);
    expect(await screen.findByText(/Kein Anbieter mit AVV/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox"));
    await waitFor(() => expect(calls).toContain("PUT"));
  });
});

describe("PayerIbanButton (M12-03)", () => {
  it("proposes the payer IBAN for the chosen contact", async () => {
    const posts: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      if (init?.method === "POST") {
        posts.push(String(init.body));
        return jsonResponse({ bank_account_id: "b1", contact_id: "c1", iban_suffix: "3000", approval_status: "pending" }, 201);
      }
      return jsonResponse({ proposable: true, iban_known: false, iban_suffix: "3000", contacts: [{ contact_id: "c1", display_name: "Erika Muster" }] });
    });
    renderIntl(<PayerIbanButton txId={TX} />);
    await userEvent.click(screen.getByRole("button", { name: "Zahler-IBAN vorschlagen" }));
    expect(await screen.findByText("IBAN endet auf 3000")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Zur Freigabe vorschlagen" }));
    expect(await screen.findByText("IBAN zur Freigabe vorgeschlagen.")).toBeInTheDocument();
    expect(posts[0]).toContain("c1");
  });

  it("says when the IBAN is already known", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ proposable: false, iban_known: true, iban_suffix: "3000", contacts: [] }));
    renderIntl(<PayerIbanButton txId={TX} />);
    await userEvent.click(screen.getByRole("button", { name: "Zahler-IBAN vorschlagen" }));
    expect(await screen.findByText("IBAN bereits bekannt")).toBeInTheDocument();
  });
});

describe("BankSyncSettingsCard (M11-05)", () => {
  it("saves the sync hour and starts a full sync", async () => {
    const calls: { url: string; method: string; body?: string }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, method: init?.method ?? "GET", body: init?.body as string | undefined });
      if (url.endsWith("/sync/run")) return jsonResponse({ connections: 2, not_configured: 1, queued: 3 }, 202);
      return jsonResponse({ sync_hour: init?.method === "PUT" ? 4 : 6, configured: init?.method === "PUT" });
    });
    renderIntl(<BankSyncSettingsCard canEdit canRun />);
    const select = await screen.findByRole("combobox");
    await waitFor(() => expect(select).not.toBeDisabled());
    await userEvent.selectOptions(select, "4");
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PUT")?.body).toContain('"sync_hour":4');
    await userEvent.click(screen.getByRole("button", { name: "Jetzt alle Konten abrufen" }));
    expect(await screen.findByText(/2 Verbindungen, 3 Konten/)).toBeInTheDocument();
  });
});

describe("BankSyncSettingsCard consent switch (T03-02)", () => {
  it("shows the switch off by default and saves it", async () => {
    const calls: { url: string; method: string; body?: string }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, method: init?.method ?? "GET", body: init?.body as string | undefined });
      if (url.endsWith("/consent-sync/settings")) return jsonResponse({ enabled: init?.method === "PUT" });
      return jsonResponse({ sync_hour: 6, configured: false });
    });
    renderIntl(<BankSyncSettingsCard canEdit canRun={false} />);
    const box = await screen.findByRole("checkbox");
    await waitFor(() => expect(box).not.toBeDisabled());
    expect(box).not.toBeChecked();
    await userEvent.click(box);
    await waitFor(() => expect(box).toBeChecked());
    expect(calls.find((c) => c.method === "PUT")?.body).toContain('"enabled":true');
  });
});

describe("AutoPostingDigests (M12-02)", () => {
  it("lists digests and confirms one", async () => {
    let confirmed = false;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (init?.method === "POST") {
        confirmed = true;
        return jsonResponse({});
      }
      return jsonResponse([
        { id: "d1", legal_entity_id: "le", week_start: "2026-09-21", auto_posted: 12, sampled: 5, reviews_open: 0, findings: 0, reconciliation_ok: true, confirmed_at: confirmed ? "2026-09-29T08:00:00Z" : null },
      ]);
    });
    renderIntl(<AutoPostingDigests canReview />);
    expect(await screen.findByText("21.09.2026")).toBeInTheDocument();
    expect(screen.getByText("ohne Differenz")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Bestätigen" }));
    expect(await screen.findByText(/bestätigt am/)).toBeInTheDocument();
  });
});
