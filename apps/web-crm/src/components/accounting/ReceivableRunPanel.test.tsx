import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ReceivableRunPanel } from "./ReceivableRunPanel";

const run = (status: string, itemStatus: string) => ({
  id: "0192abcd-0000-7000-8000-000000000001",
  period_month: "2026-03-01",
  status,
  totals: { count: 1, [itemStatus]: { count: 1, amount: "300.00" } },
  items: [
    { contract_id: "c1", payment_type_code: "hoa_fee", amount: "300.00", due_date: "2026-03-03", status: itemStatus, message: null },
  ],
});

describe("ReceivableRunPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("previews, asks for confirmation and posts", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(run("preview", "ready"), 201))
      .mockResolvedValueOnce(jsonResponse(run("posted", "posted")));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderIntl(<ReceivableRunPanel initialMonth="2026-03" />);
    await userEvent.click(screen.getByText("Vorschau erstellen"));
    expect(await screen.findByText("03.03.2026")).toBeInTheDocument();
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ period_month: "2026-03-01" });
    await userEvent.click(screen.getByRole("button", { name: /1 Sollstellungen buchen/ }));
    await waitFor(() => expect(screen.getByTestId("run-status")).toHaveTextContent("gebucht"));
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain("/post");
  });

  it("does not post without confirmation and shows API errors", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(run("preview", "ready"), 201))
      .mockResolvedValueOnce(jsonResponse({ title: "Konflikt", status: 409, detail: "Vorschau veraltet" }, 409));
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    renderIntl(<ReceivableRunPanel initialMonth="2026-03" />);
    await userEvent.click(screen.getByText("Vorschau erstellen"));
    const post = await screen.findByRole("button", { name: /buchen/ });
    await userEvent.click(post);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await userEvent.click(post);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(confirm).toHaveBeenCalledTimes(2);
  });
  it("lists earlier runs of the month and shows the difference to a posted item", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonResponse([{ id: "r1", period_month: "2026-03-01", status: "preview", created_at: "2026-03-02T08:00:00Z" }]),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          ...run("preview", "manual"),
          items: [
            {
              contract_id: "c1",
              payment_type_code: "hoa_fee",
              amount: "320.00",
              due_date: "2026-03-03",
              status: "manual",
              message: "Planänderung nach Buchung",
              contract_version: 1,
              basis_valid_from: "2026-03-01",
              difference_amount: "20.00",
            },
          ],
        }),
      );
    renderIntl(<ReceivableRunPanel initialMonth="2026-03" />);
    await userEvent.click(screen.getByText("Frühere Läufe laden"));
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("receivable-runs?period_month=2026-03-01");
    await userEvent.click(await screen.findByRole("button", { name: "Öffnen" }));
    expect(await screen.findByText(/Differenz 20,00/)).toBeInTheDocument();
    expect(screen.getByText("Grundlage ab 01.03.2026, Vertragsversion 1")).toBeInTheDocument();
  });
});
