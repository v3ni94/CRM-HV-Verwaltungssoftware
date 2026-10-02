import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AutoPostingDigests } from "./AutoPostingDigests";
import { ClarificationOpenButton } from "./ClarificationOpenButton";
import { PaymentBankConfigCard } from "./PaymentBankConfigCard";
import { PaymentBatchBankStatus } from "./PaymentBatchBankStatus";
import { TransactionCandidates } from "./TransactionCandidates";

const ID = "0192abcd-0000-7000-8000-0000000000a1";
const account = { id: ID, property_id: "p", property_number: "101", property_name: "Haus", legal_entity_id: "l", legal_entity_name: "HVM", kind: "operating", iban_masked: "DE02 **** 2051", bank_name: "Bank", holder: "WEG" };
const config = {
  property_bank_account_id: ID,
  pain001_version: "pain.001.001.09",
  pain008_version: "pain.008.001.02",
  submission_channel: "file",
  confirmed_with_bank_on: null,
  notes: null,
  supported: { pain001: ["pain.001.001.09", "pain.001.001.03"], pain008: ["pain.008.001.02", "pain.008.001.08"], channels: ["file", "fints", "ebics"] },
};

afterEach(() => vi.unstubAllGlobals());

describe("PaymentBankConfigCard (GAI-403)", () => {
  it("loads the config of the chosen account and saves with PUT", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([account]))
      .mockResolvedValueOnce(jsonResponse(config))
      .mockResolvedValueOnce(jsonResponse({ ...config, pain008_version: "pain.008.001.08" }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<PaymentBankConfigCard canApprove />);
    await userEvent.selectOptions(await screen.findByLabelText("Bankkonto"), ID);
    await userEvent.selectOptions(await screen.findByLabelText("Version pain.008"), "pain.008.001.08");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByText("Zahlungsformat gespeichert.")).toBeInTheDocument();
    expect(fetchMock.mock.calls[1]?.[0]).toBe(`/api/bff/banking/payment-bank-config/${ID}`);
    expect(fetchMock.mock.calls[2]?.[1]?.method).toBe("PUT");
    expect(JSON.parse(fetchMock.mock.calls[2]?.[1]?.body as string).pain008_version).toBe("pain.008.001.08");
  });

  it("is read only without the approval right", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(jsonResponse([account])).mockResolvedValueOnce(jsonResponse(config)));
    renderIntl(<PaymentBankConfigCard canApprove={false} />);
    await userEvent.selectOptions(await screen.findByLabelText("Bankkonto"), ID);
    expect(await screen.findByText("Ändern braucht das Freigaberecht Bank.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Speichern" })).toBeNull();
  });

  it("shows the API error on save", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse([account]))
        .mockResolvedValueOnce(jsonResponse(config))
        .mockResolvedValueOnce(jsonResponse({ title: "Validation", status: 422, detail: "pain.001-Version nicht unterstützt." }, 422)),
    );
    renderIntl(<PaymentBankConfigCard canApprove />);
    await userEvent.selectOptions(await screen.findByLabelText("Bankkonto"), ID);
    await userEvent.click(await screen.findByRole("button", { name: "Speichern" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("PaymentBatchBankStatus (GAI-404)", () => {
  it("renders nothing without the approval right", () => {
    renderIntl(<PaymentBatchBankStatus batchId={ID} canApprove={false} />);
    expect(screen.queryByTestId("batch-bank-status")).toBeNull();
  });

  it("offers no execution or return status and posts the feedback", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([{ id: "o1" }, { id: "o2" }]));
    vi.stubGlobal("fetch", fetchMock);
    const onDone = vi.fn();
    renderIntl(<PaymentBatchBankStatus batchId={ID} canApprove onDone={onDone} />);
    await userEvent.click(screen.getByRole("button", { name: "Bankrückmeldung erfassen" }));
    const options = screen.getAllByRole("option").map((o) => o.getAttribute("value"));
    expect(options).toEqual(["submitted", "accepted_by_bank", "rejected"]);
    await userEvent.click(screen.getByRole("button", { name: "Erfassen" }));
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/bff/banking/payment-batches/${ID}/bank-status`);
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ status: "accepted_by_bank", reason: null });
    expect(await screen.findByText("Rückmeldung erfasst, betroffene Aufträge: 2.")).toBeInTheDocument();
    expect(onDone).toHaveBeenCalled();
  });

  it("requires a reason for a rejection", async () => {
    vi.stubGlobal("fetch", vi.fn());
    renderIntl(<PaymentBatchBankStatus batchId={ID} canApprove />);
    await userEvent.click(screen.getByRole("button", { name: "Bankrückmeldung erfassen" }));
    await userEvent.selectOptions(screen.getByLabelText("Rückmeldung der Bank"), "rejected");
    expect(screen.getByRole("button", { name: "Erfassen" })).toBeDisabled();
  });
});

describe("TransactionCandidates (GAI-405)", () => {
  it("shows candidates with reasons and the unambiguous mark", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        candidates: [{ open_item_id: "oi1", account_id: "a", contract_id: null, remaining: "80.00", score: 90, reasons: ["Betrag stimmt überein"] }],
        unambiguous_open_item_id: "oi1",
        note: "x",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<TransactionCandidates txId={ID} />);
    await userEvent.click(screen.getByRole("button", { name: "Vorschläge" }));
    expect(await screen.findByText("Betrag stimmt überein")).toBeInTheDocument();
    expect(screen.getByText("eindeutig")).toBeInTheDocument();
    expect(screen.getByText(/keine Buchung/)).toBeInTheDocument();
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/bff/banking/transactions/${ID}/candidates`);
    expect(fetchMock.mock.calls[0]?.[1]?.method ?? "GET").toBe("GET");
  });

  it("shows the empty state and the API error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ candidates: [], unambiguous_open_item_id: null, note: "n" })));
    const { unmount } = renderIntl(<TransactionCandidates txId={ID} />);
    await userEvent.click(screen.getByRole("button", { name: "Vorschläge" }));
    expect(await screen.findByText("Kein passender offener Posten gefunden.")).toBeInTheDocument();
    unmount();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "x", status: 404, detail: "x" }, 404)));
    renderIntl(<TransactionCandidates txId={ID} />);
    await userEvent.click(screen.getByRole("button", { name: "Vorschläge" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("ClarificationOpenButton (GAI-406)", () => {
  it("needs a reason and posts it", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: "c1" }, 201));
    vi.stubGlobal("fetch", fetchMock);
    const onOpened = vi.fn();
    renderIntl(<ClarificationOpenButton txId={ID} onOpened={onOpened} />);
    await userEvent.click(screen.getByRole("button", { name: "Als unbelegt melden" }));
    expect(screen.getByRole("button", { name: "Melden" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Begründung"), "Beleg fehlt");
    await userEvent.click(screen.getByRole("button", { name: "Melden" }));
    expect(await screen.findByText("Klärung eröffnet")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/bff/banking/transactions/${ID}/clarification`);
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ reason: "Beleg fehlt" });
    expect(onOpened).toHaveBeenCalled();
  });

  it("shows the API error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403)));
    renderIntl(<ClarificationOpenButton txId={ID} />);
    await userEvent.click(screen.getByRole("button", { name: "Als unbelegt melden" }));
    await userEvent.type(screen.getByLabelText("Begründung"), "Beleg fehlt");
    await userEvent.click(screen.getByRole("button", { name: "Melden" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("AutoPostingDigests build (GAI-407)", () => {
  const digest = { id: "d1", legal_entity_id: "le", week_start: "2026-09-21", auto_posted: 1, sampled: 0, reviews_open: 0, findings: 0, reconciliation_ok: true, confirmed_at: null };

  it("builds the digest of the chosen week and reloads", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse([digest]))
      .mockResolvedValueOnce(jsonResponse([digest]));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<AutoPostingDigests canReview />);
    const button = await screen.findByRole("button", { name: "Digest erzeugen" });
    expect(button).toBeDisabled();
    await act(async () => {
      await userEvent.type(screen.getByLabelText("Woche ab (Montag)"), "2026-09-21");
    });
    await userEvent.click(button);
    await waitFor(() => expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/bff/banking/auto-posting/digests/build"));
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe("POST");
    expect(JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string)).toEqual({ week_start: "2026-09-21" });
    expect(await screen.findByText("Digest erzeugt oder aktualisiert: 1.")).toBeInTheDocument();
  });

  it("hides the build form without the review right", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([])));
    renderIntl(<AutoPostingDigests canReview={false} />);
    await screen.findByText("Kein Wochendigest vorhanden.");
    expect(screen.queryByTestId("digest-build")).toBeNull();
  });
});
