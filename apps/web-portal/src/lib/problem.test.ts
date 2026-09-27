// @vitest-environment node
import { VERSION_CONFLICT_MESSAGE, fieldPath, problemMessage } from "./problem";

describe("fieldPath", () => {
  it("strips the leading body segment and joins the remaining path", () => {
    expect(fieldPath(["body", "emails", 0, "email"])).toBe("emails.0.email");
    expect(fieldPath(["body", "name"])).toBe("name");
  });

  it("keeps non-body locations as they are", () => {
    expect(fieldPath(["query", "page"])).toBe("query.page");
    expect(fieldPath(["name"])).toBe("name");
  });

  it("returns null for an empty path", () => {
    expect(fieldPath([])).toBeNull();
    expect(fieldPath(["body"])).toBeNull();
  });
});

describe("problemMessage", () => {
  it("prefers the detail, then the title of the problem", () => {
    expect(problemMessage({ title: "Fehler", detail: "Die Einheit ist bereits vergeben." }, 409)).toBe(
      "Die Einheit ist bereits vergeben.",
    );
    expect(problemMessage({ title: "Nicht gefunden", detail: null }, 404)).toBe("Nicht gefunden");
  });

  it("always uses the fixed version conflict text for 412", () => {
    expect(problemMessage({ title: "Precondition Failed", detail: "irgendwas" }, 412)).toBe(VERSION_CONFLICT_MESSAGE);
    expect(problemMessage({ status: 412 })).toBe(VERSION_CONFLICT_MESSAGE);
  });

  it("falls back to the German default text per status code", () => {
    expect(problemMessage(null, 401)).toBe("Die Sitzung ist abgelaufen. Bitte erneut anmelden.");
    expect(problemMessage(null, 422)).toBe("Bitte die markierten Angaben prüfen.");
    expect(problemMessage({ status: 403 })).toBe("Für diese Aktion fehlt die Berechtigung.");
  });

  it("uses the generic unavailable text for unknown status codes", () => {
    expect(problemMessage(null, 0)).toBe(
      "Die Schnittstelle ist derzeit nicht erreichbar. Bitte später erneut versuchen.",
    );
    expect(problemMessage({}, 500)).toBe(
      "Die Schnittstelle ist derzeit nicht erreichbar. Bitte später erneut versuchen.",
    );
  });

  it("lets the explicit status win over the problem status", () => {
    expect(problemMessage({ status: 404 }, 401)).toBe("Die Sitzung ist abgelaufen. Bitte erneut anmelden.");
  });
});
