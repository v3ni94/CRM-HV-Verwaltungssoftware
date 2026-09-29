import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { HandoverFill, parseDecimal } from "./HandoverFill";
import { ID, protocol } from "./HandoverFill.test.fixture";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

describe("HandoverFill", () => {
  afterEach(() => vi.restoreAllMocks());

  it("adds a room through the portal BFF and reloads", async () => {
    const calls: { url: string; method: string; body: string | null }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: typeof init?.body === "string" ? init.body : null });
      if (method === "POST" && url.endsWith("/rooms")) {
        return jsonResponse({ id: "0192abcd-0000-7000-8000-000000000071", name: "Küche" }, 201);
      }
      if (method === "GET") {
        return jsonResponse(
          protocol({
            rooms: [
              {
                id: "0192abcd-0000-7000-8000-000000000071",
                name: "Küche",
                room_type: null,
                condition: "ok",
                comment: null,
                sort_order: 0,
              },
            ],
            hints: [],
          }),
        );
      }
      return jsonResponse({}, 200);
    });
    renderIntl(<HandoverFill initial={protocol()} />);
    expect(screen.getByText("Keine Einträge.")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Raum hinzufügen"));
    await userEvent.type(screen.getByLabelText("Bezeichnung"), "Küche");
    await userEvent.click(screen.getByText("Speichern"));
    await waitFor(() => expect(screen.getByText("Küche")).toBeInTheDocument());
    const post = calls.find((c) => c.method === "POST");
    expect(post?.url).toBe(`/api/bff/portal/handover/${ID}/rooms`);
    expect(JSON.parse(post?.body ?? "{}")).toMatchObject({ name: "Küche" });
  });

  it("offers no internal fields and no internal flag on remarks", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}, 200));
    renderIntl(<HandoverFill initial={protocol({ current_step: "notes" })} />);
    await userEvent.click(screen.getByText("Bemerkung hinzufügen"));
    expect(screen.queryByLabelText(/intern/i)).not.toBeInTheDocument();
    await userEvent.click(screen.getByText("Objekt"));
    expect(screen.queryByLabelText("Verwaltungsnummer")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Straße")).toHaveValue("Portalweg");
  });

  it("shows the hints before completing and offers the forced completion", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}, 200));
    renderIntl(<HandoverFill initial={protocol({ current_step: "summary" })} />);
    await userEvent.click(screen.getByText("Protokoll verbindlich abschließen"));
    expect(screen.getByTestId("hints")).toHaveTextContent("Es wurden keine Räume erfasst.");
    expect(screen.getByText("Trotz Hinweisen verbindlich abschließen")).toBeInTheDocument();
    expect(screen.queryByTestId("confirm-sheet")).toBeNull();
  });

  it("is read only once the access is read or the protocol is locked", () => {
    renderIntl(
      <HandoverFill
        initial={protocol({
          status: "completed",
          locked: true,
          finalized: true,
          current_step: "summary",
          access: { right: "read", valid_to: "2026-10-09" },
        })}
      />,
    );
    expect(screen.getByText(/kann nicht mehr geändert werden/)).toBeInTheDocument();
    expect(screen.queryByText("Protokoll verbindlich abschließen")).not.toBeInTheDocument();
    expect(screen.getByText("Protokoll als PDF")).toHaveAttribute(
      "href",
      `/api/portal-files/portal/handover/${ID}/pdf`,
    );
    expect(screen.getByText(/abrufbar bis 09.10.2026/)).toBeInTheDocument();
  });
});

describe("HandoverFill on phone and tablet (M31 WP5)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders the sections as 44 px tabs and opens the PDF in the same tab", () => {
    renderIntl(<HandoverFill initial={protocol({ current_step: "summary" })} />);
    const nav = screen.getByRole("navigation", { name: "Abschnitte" });
    for (const tab of nav.querySelectorAll("button")) expect(tab.className).toContain("min-h-11");
    expect(screen.getByRole("button", { name: "Prüfung und Abschluss" })).toHaveAttribute("aria-current", "page");
    const pdf = screen.getByText("Vorschau (Entwurf)");
    expect(pdf).toHaveAttribute("href", `/api/portal-files/portal/handover/${ID}/pdf`);
    expect(pdf).not.toHaveAttribute("target");
    expect(document.querySelector("a[target='_blank']")).toBeNull();
  });

  it("completes through the ConfirmSheet instead of window.confirm", async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      calls.push(`${init?.method ?? "GET"} ${String(input)}`);
      if (String(input).endsWith("/complete")) {
        return jsonResponse(protocol({ hints: [], status: "completed", locked: true, finalized: true, current_step: "summary" }));
      }
      return jsonResponse({}, 200);
    });
    const confirmSpy = vi.spyOn(window, "confirm");
    renderIntl(<HandoverFill initial={protocol({ current_step: "summary", hints: [] })} />);
    await userEvent.click(screen.getByText("Protokoll verbindlich abschließen"));
    const sheet = screen.getByRole("alertdialog");
    expect(sheet).toHaveTextContent("Ist die Übergabe vollständig abgeschlossen?");
    expect(calls.filter((c) => c.includes("/complete"))).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Ja, abschließen" }));
    await waitFor(() => expect(calls).toContain(`POST /api/bff/portal/handover/${ID}/complete`));
    expect(confirmSpy).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByText(/kann nicht mehr geändert werden/)).toBeInTheDocument());
  });

  it("captures the photo with the new defect: camera and gallery inputs, POST before the upload", async () => {
    const calls: { method: string; url: string; body: unknown }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push({ method, url, body: init?.body });
      if (method === "POST" && url.endsWith("/defects")) return jsonResponse({ id: "0192abcd-0000-7000-8000-000000000099" }, 201);
      if (method === "POST" && url.endsWith("/documents")) return jsonResponse({ id: "doc" }, 201);
      return jsonResponse(protocol({ current_step: "defects" }));
    });
    renderIntl(<HandoverFill initial={protocol({ current_step: "defects" })} />);
    await userEvent.click(screen.getByText("Mangel hinzufügen"));
    const camera = screen.getByTestId("photo-input-camera") as HTMLInputElement;
    const gallery = screen.getByTestId("photo-input-gallery") as HTMLInputElement;
    expect(camera).toHaveAttribute("capture", "environment");
    expect(camera.accept).toContain("image/heic");
    expect(gallery).not.toHaveAttribute("capture");
    expect(gallery).toHaveAttribute("multiple");
    await userEvent.type(screen.getByLabelText("Titel"), "Riss");
    await userEvent.upload(gallery, new File(["x"], "riss.jpg", { type: "image/jpeg" }));
    expect(screen.getByText("riss.jpg")).toBeInTheDocument();
    expect(screen.getByText("Wartet")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Speichern"));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/documents"))).toBe(true));
    const posts = calls.filter((c) => c.method === "POST").map((c) => c.url);
    expect(posts[0]).toBe(`/api/bff/portal/handover/${ID}/defects`);
    expect(posts[1]).toBe(`/api/bff/portal/handover/${ID}/documents`);
    const form = calls.find((c) => c.url.endsWith("/documents"))?.body as FormData;
    expect(form.get("section")).toBe("defects");
    expect(form.get("item_id")).toBe("0192abcd-0000-7000-8000-000000000099");
  });

  it("names the right consequence when removing a photo (version 1 deletes, later versions keep the file)", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}, 200));
    const doc = { id: "doc1", title: "Zähler", filename: "z.jpg", mime_type: "image/jpeg", size: 1, kind: "photo" as const, section: "meters", item_id: "m1", created_at: "2026-09-20T10:00:00Z" };
    const meter = { id: "m1", meter_type: "electricity", custom_type: null, number: "1", value: "1", unit: "kWh", read_on: null, location: null, comment: null };
    const { unmount } = renderIntl(<HandoverFill initial={protocol({ current_step: "meters", meters: [meter], documents: [doc] })} />);
    await userEvent.click(screen.getByRole("button", { name: "Foto entfernen" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent("Die Datei wird aus diesem Protokoll gelöscht.");
    await userEvent.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(fetch).not.toHaveBeenCalled();
    unmount();
    renderIntl(<HandoverFill initial={protocol({ current_step: "meters", version: 2, meters: [meter], documents: [doc] })} />);
    await userEvent.click(screen.getByRole("button", { name: "Foto entfernen" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent("Die Datei bleibt in der früheren Fassung erhalten.");
    await userEvent.click(screen.getByRole("button", { name: "Foto Zähler vergrößern" }));
    expect(screen.getByRole("dialog", { name: "Zähler" })).toBeInTheDocument();
  });
});

describe("parseDecimal", () => {
  it("accepts German input and the API format without changing the value", () => {
    expect(parseDecimal("1.500,50")).toBe("1500.50");
    expect(parseDecimal("1500.00")).toBe("1500.00");
  });
});
