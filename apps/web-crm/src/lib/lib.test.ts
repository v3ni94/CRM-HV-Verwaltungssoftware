// @vitest-environment node
import { isValidIban } from "./contact-schema";
import { originAllowed } from "./csrf";
import { formatConfidence, formatDate, formatEur } from "./format";
import { VERSION_CONFLICT_MESSAGE, fieldPath, problemMessage } from "./problem";
import { cookieOptions, isSecureHost, parseContext } from "./session";

describe("IBAN check (mirrors the API)", () => {
  it.each([
    ["DE89370400440532013000", true],
    ["de89 3704 0044 0532 0130 00", true],
    ["DE89370400440532013001", false],
    ["DE8937040044053201300", false],
    ["XX", false],
  ])("%s -> %s", (iban, ok) => expect(isValidIban(iban)).toBe(ok));
});

describe("session cookies", () => {
  it("are httpOnly and SameSite=Strict, Secure except on localhost", () => {
    expect(cookieOptions(true, 60)).toEqual({ httpOnly: true, sameSite: "strict", secure: true, path: "/", maxAge: 60 });
    expect(isSecureHost("localhost:3000")).toBe(false);
    expect(isSecureHost("127.0.0.1:3000")).toBe(false);
    expect(isSecureHost("crm.localhost")).toBe(false);
    expect(isSecureHost("crm.mueller-holding.ag")).toBe(true);
  });

  it("parses the context cookie defensively", () => {
    expect(parseContext("kaputt")).toEqual({ tenantId: null, tenants: [] });
    expect(parseContext(JSON.stringify({ tenantId: "a", tenants: [{ id: "a", name: "A" }, { id: 1 }] }))).toEqual({
      tenantId: "a",
      tenants: [{ id: "a", name: "A" }],
    });
  });
});

describe("CSRF origin check", () => {
  const req = (headers: Record<string, string>) => new Request("http://crm.localhost/api/x", { method: "POST", headers });
  it("accepts same origin only", () => {
    expect(originAllowed(req({ host: "crm.localhost", origin: "http://crm.localhost" }))).toBe(true);
    expect(originAllowed(req({ host: "crm.localhost", origin: "http://evil.example" }))).toBe(false);
    expect(originAllowed(req({ host: "crm.localhost" }))).toBe(false);
  });
});

describe("problem details", () => {
  it("maps API locations to form paths", () => {
    expect(fieldPath(["body", "emails", 0, "email"])).toBe("emails.0.email");
    expect(fieldPath(["body"])).toBeNull();
  });
  it("uses the API text, but a fixed text for 412", () => {
    expect(problemMessage({ title: "Eingaben ungültig", detail: "Bitte prüfen." })).toBe("Bitte prüfen.");
    expect(problemMessage({ title: "x" }, 412)).toBe(VERSION_CONFLICT_MESSAGE);
    expect(problemMessage(null, 403)).toBe("Für diese Aktion fehlt die Berechtigung.");
  });
});

describe("formats", () => {
  it("shows dates as TT.MM.JJJJ", () => {
    expect(formatDate("2026-09-23")).toBe("23.09.2026");
    expect(formatDate("2026-09-22T23:30:00Z")).toBe("23.09.2026");
  });
});

describe("money format without float", () => {
  it("formats decimal strings as 1.234,56 EUR and rounds half up", () => {
    expect(formatEur("1234.5")).toBe("1.234,50 EUR");
    expect(formatEur("0.005")).toBe("0,01 EUR");
    expect(formatEur("999999.995")).toBe("1.000.000,00 EUR");
    expect(formatEur("-12")).toBe("-12,00 EUR");
    expect(formatEur(null)).toBe("");
    expect(formatConfidence("0.873")).toBe("87 %");
  });
});
