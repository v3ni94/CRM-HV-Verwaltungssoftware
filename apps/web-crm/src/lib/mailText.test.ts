import { formatBytes, isValidAddress, parseAddressList, splitQuoted } from "./mailText";

describe("splitQuoted", () => {
  it("folds quoted lines and reply headers", () => {
    const text = "Danke für die Antwort.\n\nAm 24.09.2026 um 09:00 schrieb Verwaltung:\n> Wir kümmern uns.\n> Gruß";
    const { visible, quoted } = splitQuoted(text);
    expect(visible).toBe("Danke für die Antwort.");
    expect(quoted).toContain("> Wir kümmern uns.");
  });

  it("folds outlook style separators", () => {
    const { visible, quoted } = splitQuoted("Neu\n-----Ursprüngliche Nachricht-----\nVon: a@b.de\nalt");
    expect(visible).toBe("Neu");
    expect(quoted?.startsWith("-----Ursprüngliche")).toBe(true);
  });

  it("keeps text without quotes intact", () => {
    expect(splitQuoted("Nur Text\nZeile 2")).toEqual({ visible: "Nur Text\nZeile 2", quoted: null });
    expect(splitQuoted(null)).toEqual({ visible: "", quoted: null });
  });
});

describe("formatBytes and addresses", () => {
  it("formats sizes in German notation", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2,0 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5,0 MB");
    expect(formatBytes(null)).toBe("");
  });

  it("parses and validates address lists", () => {
    expect(parseAddressList("a@x.de, b@y.de;c@z.de\n")).toEqual(["a@x.de", "b@y.de", "c@z.de"]);
    expect(isValidAddress("a@x.de")).toBe(true);
    expect(isValidAddress("kein mail")).toBe(false);
  });
});
