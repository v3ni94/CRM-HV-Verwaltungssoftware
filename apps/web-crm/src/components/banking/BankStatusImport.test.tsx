import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BankStatusImport } from "./BankStatusImport";

function upload() {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  const file = new File(["<Document/>"], "status.xml", { type: "text/xml" });
  Object.defineProperty(file, "text", { value: () => Promise.resolve("<Document/>") });
  return act(async () => {
    await userEvent.upload(input, file);
  });
}

describe("BankStatusImport", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts the XML to the BFF and lists the report lines", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ id: "r1", kind: "pain.002", created: true, result: [{ end_to_end_id: "E2E-1", reported: "RJCT", reason_code: "AC04", amount: "10.00", result: "offen" }] }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<BankStatusImport />);
    await upload();
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/accounting/payment-runs/bank-status-reports");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ xml: "<Document/>" });
    expect(await screen.findByRole("status")).toHaveTextContent("E2E-1 RJCT (AC04)");
  });

  it("shows the error on 403", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403)));
    renderIntl(<BankStatusImport />);
    await upload();
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.queryByRole("status")).toBeNull();
  });
});
