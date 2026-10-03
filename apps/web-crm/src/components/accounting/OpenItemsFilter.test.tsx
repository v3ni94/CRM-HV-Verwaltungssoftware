import { screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { OpenItemsFilter, parseAccountFilter } from "./OpenItemsFilter";

vi.mock("next-intl/server", async () => {
  const { default: de } = await import("../../../messages/de.json");
  return {
    getTranslations: async (namespace: string) => (key: string) => {
      const raw = `${namespace}.${key}`.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], de);
      if (typeof raw !== "string") throw new Error(`INSUFFICIENT_PATH ${namespace}.${key}`);
      return raw;
    },
  };
});

const ID = "01920000-0000-7000-8000-0000000000bb";
const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockImplementation(() => Promise.resolve(jsonResponse([{ id: "f1", resource: "open_items", name: "Mieter 1", params: { op_account: ID } }])));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("parseAccountFilter", () => {
  it("accepts only UUIDs", () => {
    expect(parseAccountFilter(ID)).toBe(ID);
    expect(parseAccountFilter("abc")).toBe("");
    expect(parseAccountFilter(undefined)).toBe("");
  });
});

describe("OpenItemsFilter", () => {
  it("renders the account select, keeps parameters and loads saved filters of open_items", async () => {
    const ui = await OpenItemsFilter({ basePath: "/buchhaltung/x", current: ID, accounts: [{ id: ID, number: "10001", name: "Mieter" }], keep: { property: "p1" } });
    const { container } = renderIntl(ui);
    expect((container.querySelector("#op-account") as HTMLSelectElement).value).toBe(ID);
    expect(container.querySelector('input[type="hidden"][name="property"]')).not.toBeNull();
    await waitFor(() => expect(screen.getByRole("link", { name: "Mieter 1" }).getAttribute("href")).toBe(`/buchhaltung/x?op_account=${ID}`));
    expect(String(fetchMock.mock.calls[0]![0])).toContain("resource=open_items");
  });
});
