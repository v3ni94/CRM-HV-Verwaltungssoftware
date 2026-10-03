import { render, screen, waitFor } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import de from "../../../messages/de.json";
import { AddressHistoryPanel } from "./AddressHistoryPanel";

const ID = "0190a3b4-0000-7000-8000-000000000001";

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

function renderPanel() {
  return render(
    <NextIntlClientProvider locale="de" messages={de}>
      <AddressHistoryPanel contactId={ID} />
    </NextIntlClientProvider>,
  );
}

const row = (city: string, extra: Record<string, unknown> = {}) => ({
  id: `${city}-id`,
  street: "Weg",
  house_number: "1",
  postal_code: "40721",
  city,
  is_primary: false,
  valid_from: null,
  valid_to: null,
  superseded_at: null,
  ...extra,
});

afterEach(() => vi.unstubAllGlobals());

describe("AddressHistoryPanel (AN05)", () => {
  it("shows the hint while the switch is off", async () => {
    mockFetch(422, { code: "MHVP-CONT-0034", status: 422, title: "x" });
    renderPanel();
    expect(await screen.findByTestId("address-history-off")).toBeTruthy();
  });

  it("lists current and closed addresses and queries a cut off date", async () => {
    const fetchMock = mockFetch(200, {
      history_available: true,
      as_of: null,
      items: [
        row("Erkrath", { is_primary: true, valid_from: "2026-10-03" }),
        row("Hilden", { valid_to: "2026-10-02", superseded_at: "2026-10-03T08:00:00Z" }),
      ],
    });
    renderPanel();
    expect(await screen.findAllByTestId("address-history-row")).toHaveLength(2);
    expect(screen.getByText(/ersetzt/)).toBeTruthy();
    expect(String(fetchMock.mock.calls[0]![0])).toContain(`/api/bff/contacts/${ID}/addresses?include_history=true`);
    fireEvent.change(screen.getByTestId("address-history-as-of"), { target: { value: "2026-01-01" } });
    await waitFor(() => expect(String(fetchMock.mock.calls.at(-1)![0])).toContain("as_of=2026-01-01"));
  });

  it("shows an error", async () => {
    mockFetch(500, { title: "Fehler", status: 500 });
    renderPanel();
    expect(await screen.findByRole("alert")).toBeTruthy();
  });
});
