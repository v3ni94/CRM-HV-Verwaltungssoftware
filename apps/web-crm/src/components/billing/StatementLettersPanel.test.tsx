import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { StatementLettersPanel } from "./StatementLettersPanel";

// AJ28: the gated child reads the gate state itself (own test in components/gated).
vi.mock("@/components/gated/StatementLettersSendButton", () => ({ StatementLettersSendButton: () => null }));

const ID = "0192abcd-0000-7000-8000-000000000021";
const CID = "0192abcd-0000-7000-8000-000000000022";
const ROW = {
  contract_id: CID,
  unit_number: "01",
  balance: "120.00",
  delivered_at: null,
  delivery_method: null,
  objection_deadline_orientation: null,
};

describe("StatementLettersPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows a hint without snapshot and loads nothing", () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderIntl(<StatementLettersPanel id={ID} status="draft" hasSnapshot={false} />);
    expect(screen.getByText("Noch kein Ergebnis berechnet.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("records the access per tenant only with date and evidence", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([ROW]))
      .mockResolvedValueOnce(jsonResponse({ ...ROW, delivered_at: "2026-10-01", delivery_method: "post" }))
      .mockResolvedValueOnce(
        jsonResponse([{ ...ROW, delivered_at: "2026-10-01", delivery_method: "post", objection_deadline_orientation: "2027-10-01" }]),
      );
    renderIntl(<StatementLettersPanel id={ID} status="internally_approved" hasSnapshot />);
    expect(await screen.findByText("01")).toBeInTheDocument();
    expect(screen.getByText(/120,00/)).toBeInTheDocument();
    const save = screen.getByRole("button", { name: "Zugang erfassen" });
    expect(save).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Zugang"), "2026-10-01");
    await userEvent.type(screen.getByLabelText("Nachweis"), "Postausgangsbuch 17");
    await userEvent.click(save);
    await waitFor(() => expect(screen.getByText("01.10.2027")).toBeInTheDocument());
    const [url, init] = fetchMock.mock.calls[1] ?? [];
    expect(url).toBe(`/api/bff/statements/${ID}/results/${CID}/delivery`);
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(init?.body as string)).toEqual({
      delivery_method: "post",
      delivered_at: "2026-10-01",
      evidence: "Postausgangsbuch 17",
    });
  });

  it("files the letters as drafts and hides the access form after posting", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([ROW]))
      .mockResolvedValueOnce(jsonResponse({ letters: [{}] }, 201));
    renderIntl(<StatementLettersPanel id={ID} status="posted" hasSnapshot />);
    expect(await screen.findByText("01")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Zugang erfassen" })).toBeNull();
    await userEvent.click(screen.getByText("Anschreiben als Entwurf ablegen"));
    expect(await screen.findByText(/1 Anschreiben als Entwurf abgelegt/)).toBeInTheDocument();
  });
});
