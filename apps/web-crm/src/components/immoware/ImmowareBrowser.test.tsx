import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ImmowareBrowser } from "./ImmowareBrowser";

const contactsPage = {
  data: [
    {
      id: "01920000-0000-7000-8000-0000000000c1",
      href: "/addressbooks/default/contact-1.vcf",
      fn: "Erika Musterfrau",
      org: null,
      emails: ["erika@example.org"],
      phones: [],
      matched_contact_id: null,
    },
  ],
  meta: { page: 1, per_page: 25, total: 1 },
};

describe("ImmowareBrowser bulk actions", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("takes over all unmatched contacts and shows the result summary", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && url.includes("/contacts/take-over")) {
        return Promise.resolve(jsonResponse({ created: 1, linked: 0, skipped: 0, total: 1 }));
      }
      if (url.includes("/immoware/contacts")) return Promise.resolve(jsonResponse(contactsPage));
      return Promise.resolve(jsonResponse({ data: [], meta: { page: 1, per_page: 25, total: 0 } }));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderIntl(<ImmowareBrowser />);

    await act(async () => {
      await userEvent.click(screen.getByRole("tab", { name: "Kontakte" }));
    });
    expect(await screen.findByText("Erika Musterfrau")).toBeInTheDocument();

    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Alle uebernehmen" }));
    });

    expect(screen.getByText("1 neu angelegt, 0 verknuepft, 0 uebersprungen (von 1).")).toBeInTheDocument();
  });

  it("takes over a document folder and shows the result summary", async () => {
    const documentsPage = {
      data: [
        {
          id: "01920000-0000-7000-8000-0000000000d1",
          href: "/rechnung.pdf",
          display_name: "rechnung.pdf",
          content_type: "application/pdf",
          size: 1234,
          last_modified: null,
          is_collection: false,
        },
      ],
      meta: { page: 1, per_page: 25, total: 1 },
    };
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && url.includes("/documents/take-over-folder")) {
        return Promise.resolve(jsonResponse({ created: 1, linked: 0, failed: 0, total: 1 }));
      }
      if (url.includes("/immoware/documents")) return Promise.resolve(jsonResponse(documentsPage));
      return Promise.resolve(jsonResponse({ data: [], meta: { page: 1, per_page: 25, total: 0 } }));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderIntl(<ImmowareBrowser />);

    expect(await screen.findByText("rechnung.pdf")).toBeInTheDocument();

    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Ordner uebernehmen" }));
    });

    expect(screen.getByText("1 neu angelegt, 0 bereits uebernommen, 0 fehlgeschlagen (von 1).")).toBeInTheDocument();
  });
});
