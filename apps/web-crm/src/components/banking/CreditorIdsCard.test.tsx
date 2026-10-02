import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { CreditorIdsCard } from "./CreditorIdsCard";

const entities = [{ id: "le1", name: "WEG Musterstraße" }];

describe("CreditorIdsCard", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("saves the creditor id for the selected legal entity", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<CreditorIdsCard entities={entities} canUpdate canUpdateTenant={false} />);
    await userEvent.type(screen.getByRole("textbox"), " DE00ZZZ00000000001 ");
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/accounting/direct-debits/creditor-ids/legal-entities/le1");
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("PUT");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ sepa_creditor_id: "DE00ZZZ00000000001" });
    expect(await screen.findByRole("status")).toBeInTheDocument();
  });

  it("uses the tenant path for the fallback and sends null for an empty value", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<CreditorIdsCard entities={entities} canUpdate canUpdateTenant />);
    await userEvent.selectOptions(screen.getByRole("combobox"), "tenant");
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/accounting/direct-debits/creditor-ids/tenant");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ sepa_creditor_id: null });
  });

  it("disables saving without permission", () => {
    renderIntl(<CreditorIdsCard entities={entities} canUpdate={false} canUpdateTenant />);
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("shows the API error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403)));
    renderIntl(<CreditorIdsCard entities={entities} canUpdate canUpdateTenant />);
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
