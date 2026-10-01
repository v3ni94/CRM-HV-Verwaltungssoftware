import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DunningCaseDetails, type DunningCaseInfo } from "./DunningCaseDetails";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const CASE: DunningCaseInfo = {
  id: "c1",
  status: "sent",
  check_hints: ["Verjährung prüfen: älteste Fälligkeit 01.01.2024"],
  interest_amount: "12.50",
  interest_entry_id: null,
  interest_detail: [{ from: "2026-01-01", to: "2026-06-30", days: 181, base_rate: "2.27", spread: "5.00", rate: "7.27", amount: "12.50" }],
  interest_spread_suggestion: { profile: "verbraucher", spread: "5.00", hinweis: "Vorschlag, keine Feststellung." },
  delivery_proofs: [{ id: "p1", kind: "registered_mail", proof_date: "2026-03-01", reference: "RS 1", note: null }],
  open_items: [{ open_item_id: "oi1", due_date: "2026-01-01", remaining: "100.00" }],
};

describe("DunningCaseDetails", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows check hints, the spread proposal, the interest periods and existing proofs", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([]));
    renderIntl(<DunningCaseDetails c={CASE} />);
    expect(screen.getByTestId("dunning-hints")).toHaveTextContent("Verjährung prüfen");
    expect(screen.getByTestId("dunning-spread")).toHaveTextContent("Vorschlag für Verbraucher: 5.00 Prozentpunkte");
    expect(screen.getByTestId("dunning-interest")).toHaveTextContent("7.27 %");
    expect(screen.getByTestId("dunning-proofs")).toHaveTextContent("Einschreiben, 01.03.2026, RS 1");
    await waitFor(() => expect(screen.getByTestId("dunning-blocks")).toBeInTheDocument());
  });

  it("records a delivery proof via the API", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      if (String(url).endsWith("/delivery-proofs"))
        return jsonResponse({ id: "p2", kind: "email_receipt", proof_date: "2026-03-05", reference: null, note: null }, 201);
      return jsonResponse([]);
    });
    renderIntl(<DunningCaseDetails c={CASE} />);
    const box = screen.getByTestId("dunning-proofs");
    const add = box.querySelector("button") as HTMLButtonElement;
    expect(add).toBeDisabled();
    const date = box.querySelector('input[type="date"]') as HTMLInputElement;
    await userEvent.type(date, "2026-03-05");
    await userEvent.selectOptions(box.querySelector("select") as HTMLSelectElement, "email_receipt");
    await userEvent.click(add);
    await waitFor(() => expect(box).toHaveTextContent("E-Mail-Nachweis, 05.03.2026"));
    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/dunning-cases/c1/delivery-proofs"));
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ kind: "email_receipt", proof_date: "2026-03-05" });
  });

  it("creates the interest draft and sets and releases a block", async () => {
    const calls: string[] = [];
    let blocks: unknown[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      const u = String(url);
      calls.push(`${init?.method ?? "GET"} ${u}`);
      if (u.endsWith("/interest-draft")) return jsonResponse({ entry_id: "e1" }, 201);
      if (u.endsWith("/open-items/oi1/dunning-blocks")) {
        blocks = [{ id: "b1", open_item_id: "oi1", reason_code: "disputed", reason_label: "x", note: null, active: true, created_at: "2026-01-01" }];
        return jsonResponse(blocks[0], 201);
      }
      if (u.endsWith("/dunning-blocks/b1/release")) {
        blocks = [];
        return jsonResponse({});
      }
      return jsonResponse(blocks);
    });
    renderIntl(<DunningCaseDetails c={CASE} />);
    await userEvent.click(screen.getByRole("button", { name: "Zinsentwurf anlegen" }));
    expect(await screen.findByText("Zinsentwurf angelegt")).toBeInTheDocument();
    expect(refresh).toHaveBeenCalled();
    await userEvent.selectOptions(screen.getByLabelText("Sperrgrund"), "disputed");
    await userEvent.click(screen.getByRole("button", { name: "Sperren" }));
    await userEvent.click(await screen.findByRole("button", { name: "Aufheben" }));
    await waitFor(() => expect(calls.some((c) => c === "POST /api/bff/accounting/dunning-blocks/b1/release")).toBe(true));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Aufheben" })).toBeNull());
  });

  it("shows no spread value without a consumer flag and no draft button for zero interest", () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([]));
    renderIntl(
      <DunningCaseDetails
        c={{ ...CASE, interest_amount: "0.00", interest_detail: [], interest_spread_suggestion: { profile: null, spread: null, hinweis: "h" } }}
      />,
    );
    expect(screen.getByTestId("dunning-spread")).toHaveTextContent("Kein Vorschlag");
    expect(screen.queryByRole("button", { name: "Zinsentwurf anlegen" })).toBeNull();
  });
});
