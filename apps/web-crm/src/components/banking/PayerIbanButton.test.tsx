import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PayerIbanButton } from "./PayerIbanButton";

const candidates = {
  proposable: true,
  iban_known: false,
  iban_suffix: "1234",
  contacts: [{ contact_id: "c1", display_name: "Erika Beispiel" }],
};

describe("PayerIbanButton", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("loads candidates, then posts the proposal with the selected contact", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(candidates)).mockResolvedValueOnce(jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<PayerIbanButton txId="tx1" />);
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/banking/transactions/tx1/payer-iban");
    expect(await screen.findByTestId("payer-iban")).toBeInTheDocument();
    expect(screen.getByText("Erika Beispiel")).toBeInTheDocument();
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe("POST");
    expect(JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string)).toEqual({ contact_id: "c1" });
    expect(screen.queryByTestId("payer-iban")).toBeNull();
  });

  it("offers no proposal when the IBAN is not proposable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ ...candidates, proposable: false, iban_known: true, contacts: [] })));
    renderIntl(<PayerIbanButton txId="tx1" />);
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(screen.queryByTestId("payer-iban")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("shows the error when loading is forbidden (403)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403)));
    renderIntl(<PayerIbanButton txId="tx1" />);
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
