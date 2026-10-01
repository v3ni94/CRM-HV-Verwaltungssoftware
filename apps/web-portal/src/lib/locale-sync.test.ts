import { beforeEach, describe, expect, it, vi } from "vitest";

import { adoptAccountLocale, persistAccountLocale, readLocaleCookie } from "./locale-sync";

const fetchMock = vi.fn<typeof fetch>();
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  document.cookie = "mhvp_locale=; Max-Age=0; Path=/";
});

describe("locale sync (GA11-01)", () => {
  it("reads only supported languages from the cookie", () => {
    expect(readLocaleCookie("a=1; mhvp_locale=en")).toBe("en");
    expect(readLocaleCookie("mhvp_locale=fr")).toBeUndefined();
    expect(readLocaleCookie("")).toBeUndefined();
  });

  it("stores the choice at the account", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await persistAccountLocale("en");
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/bff/portal/me/locale");
    expect(fetchMock.mock.calls[0]![1]).toMatchObject({ method: "PATCH", body: JSON.stringify({ locale: "en" }) });
  });

  it("takes the account language into the cookie at sign-in", async () => {
    fetchMock.mockResolvedValueOnce(json({ locale: "en" })).mockResolvedValueOnce(new Response(null, { status: 204 }));
    await adoptAccountLocale();
    expect(fetchMock.mock.calls[1]![0]).toBe("/api/locale");
    expect(fetchMock.mock.calls[1]![1]).toMatchObject({ body: JSON.stringify({ locale: "en" }) });
  });

  it("does nothing when cookie and account agree", async () => {
    document.cookie = "mhvp_locale=en; Path=/";
    fetchMock.mockResolvedValueOnce(json({ locale: "en" }));
    await adoptAccountLocale();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("hands the visitor choice to an account without a language", async () => {
    document.cookie = "mhvp_locale=en; Path=/";
    fetchMock.mockResolvedValueOnce(json({ locale: null })).mockResolvedValueOnce(new Response(null, { status: 204 }));
    await adoptAccountLocale();
    expect(fetchMock.mock.calls[1]![0]).toBe("/api/bff/portal/me/locale");
  });

  it("survives a failing request", async () => {
    fetchMock.mockRejectedValue(new Error("offline"));
    await expect(adoptAccountLocale()).resolves.toBeUndefined();
  });
});
