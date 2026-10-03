import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, messages, renderIntl } from "@/test/intl";

import { PlaybookManager, type Playbook } from "./PlaybookManager";

const m = messages.MailPlaybooks;

const DRAFT: Playbook = {
  id: "pb1",
  title: "Heizungsausfall",
  category: "Technik",
  keywords: ["heizung", "kalt"],
  summary: "Vorgehen bei Heizungsausfall",
  steps: ["Mieter anrufen", "Techniker beauftragen"],
  reply_template: null,
  source_ticket_id: null,
  status: "draft",
  usage_count: 3,
  created_by: null,
};

describe("PlaybookManager", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the empty state and no write buttons for readers", () => {
    renderIntl(<PlaybookManager playbooks={[]} canWrite={false} canDelete={false} />);
    expect(screen.getByText(m.empty)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: m.new })).toBeNull();
  });

  it("hides delete without delete right but shows activate for drafts", () => {
    renderIntl(<PlaybookManager playbooks={[DRAFT]} canWrite canDelete={false} />);
    expect(screen.getByText("Heizungsausfall")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: m.activate })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: m.delete })).toBeNull();
  });

  it("creates a playbook with a normalized payload", async () => {
    const created = { ...DRAFT, id: "pb2", title: "Neu" };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(created));
    renderIntl(<PlaybookManager playbooks={[]} canWrite canDelete />);
    await userEvent.click(screen.getByRole("button", { name: m.new }));
    const save = screen.getByRole("button", { name: m.save });
    expect(save).toBeDisabled();
    await userEvent.type(screen.getByLabelText(m.titleLabel), " Neu ");
    await userEvent.type(screen.getByLabelText(m.keywords), "a, , b");
    await userEvent.type(screen.getByLabelText(m.steps), "eins{Enter}{Enter}zwei");
    await userEvent.click(save);
    expect(await screen.findByText("Neu")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/bff/mail/playbooks");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      title: "Neu",
      category: null,
      keywords: ["a", "b"],
      summary: "",
      steps: ["eins", "zwei"],
      reply_template: null,
      status: "draft",
    });
  });

  it("activates a draft via PATCH and updates the badge", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ ...DRAFT, status: "active" }));
    renderIntl(<PlaybookManager playbooks={[DRAFT]} canWrite canDelete />);
    await userEvent.click(screen.getByRole("button", { name: m.activate }));
    expect(await screen.findByText(m.status.active)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: m.activate })).toBeNull();
    expect(fetchMock.mock.calls[0]![1]?.method).toBe("PATCH");
    expect(JSON.parse(String(fetchMock.mock.calls[0]![1]?.body))).toEqual({ status: "active" });
  });

  it("deletes on success and keeps the entry with an error on failure", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementationOnce(async () => jsonResponse({ title: "Verboten", status: 403, detail: "Keine Berechtigung" }, 403))
      .mockImplementationOnce(async () => new Response(null, { status: 204 }));
    renderIntl(<PlaybookManager playbooks={[DRAFT]} canWrite canDelete />);
    await userEvent.click(screen.getByRole("button", { name: m.delete }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Heizungsausfall")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: m.delete }));
    await screen.findByText(m.empty);
    expect(String(fetchMock.mock.calls[1]![0])).toBe("/api/bff/mail/playbooks/pb1");
    expect(fetchMock.mock.calls[1]![1]?.method).toBe("DELETE");
  });

  it("edits an existing playbook with PATCH and closes the form", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ ...DRAFT, title: "Geändert" }));
    renderIntl(<PlaybookManager playbooks={[DRAFT]} canWrite canDelete />);
    await userEvent.click(screen.getByRole("button", { name: m.save }));
    const title = screen.getByLabelText(m.titleLabel);
    expect(title).toHaveValue("Heizungsausfall");
    await userEvent.clear(title);
    await userEvent.type(title, "Geändert");
    const form = title.closest("section")!;
    await userEvent.click(within(form).getByRole("button", { name: m.save }));
    expect(await screen.findByText("Geändert")).toBeInTheDocument();
    expect(screen.queryByLabelText(m.titleLabel)).toBeNull();
  });
});
