import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Proposal } from "@/lib/ai";
import { jsonResponse, renderIntl } from "@/test/intl";

import { ChatActionProposal } from "./ChatActionProposal";
import { ChatLinks, isCrmPath } from "./ChatLinks";

describe("ChatLinks", () => {
  it("renders every platform link as a CRM link with type and detail", () => {
    renderIntl(
      <ChatLinks
        links={[
          { type: "contact", id: "c1", label: "Jan Kowalski", href: "/kontakte/c1", detail: "Mieter, Köln" },
          { type: "unit", id: "u1", label: "893 Einheit 07", href: "/vermietung/einheit/u1", detail: "" },
          { type: "page", id: "/einstellungen/mandant", label: "Markenfarben", href: "/einstellungen/mandant#company-branding-title", detail: "Einstellungen" },
        ]}
      />,
    );
    expect(screen.getByRole("link", { name: "Jan Kowalski" })).toHaveAttribute("href", "/kontakte/c1");
    expect(screen.getByRole("link", { name: "893 Einheit 07" })).toHaveAttribute("href", "/vermietung/einheit/u1");
    expect(screen.getByRole("link", { name: "Markenfarben" })).toHaveAttribute("href", "/einstellungen/mandant#company-branding-title");
    expect(screen.getByText("Kontakt")).toBeInTheDocument();
    expect(screen.getByText("(Mieter, Köln)")).toBeInTheDocument();
  });

  it("renders nothing without links and never an external link", () => {
    const { container } = renderIntl(<ChatLinks links={[]} />);
    expect(container).toBeEmptyDOMElement();
    expect(isCrmPath("https://evil.example/x")).toBe(false);
    expect(isCrmPath("//evil.example/x")).toBe(false);
    expect(isCrmPath("/tickets/1")).toBe(true);
    renderIntl(<ChatLinks links={[{ type: "ticket", id: "x", label: "Fremd", href: "https://evil.example", detail: "" }]} />);
    expect(screen.queryByRole("link", { name: "Fremd" })).not.toBeInTheDocument();
    expect(screen.getByText("Fremd")).toBeInTheDocument();
  });
});

describe("ChatActionProposal", () => {
  afterEach(() => vi.restoreAllMocks());

  it("applies only on confirmation and links the changed record", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ id: "i1", summary: { kind: "contact_change", contact_id: "c1" }, items: [] }, 201));
    const proposal = {
      id: "p1",
      entity_type: "chat_action",
      decision: "pending",
      proposed: { kind: "contact_change", contact_id: "c1", contact_label: "Jan Kowalski", changes: [{ field: "phone", old: null, new: "0211 7654321" }] },
    } as unknown as Proposal;
    renderIntl(<ChatActionProposal proposal={proposal} />);
    expect(screen.getByText("Vorschlag: Kontaktdaten ändern")).toBeInTheDocument();
    expect(screen.getByText("Telefon: 0211 7654321")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Bestätigen und übernehmen" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Übernommen.");
    expect(screen.getByRole("link", { name: "Öffnen" })).toHaveAttribute("href", "/kontakte/c1");
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toContain("/api/bff/ai/proposals/p1/apply");
    expect(JSON.parse(String(init?.body))).toEqual({ chat_action: {} });
  });
});
