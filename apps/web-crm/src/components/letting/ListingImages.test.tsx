import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ListingImages, type ListingImage } from "./ListingImages";

const LISTING_ID = "0192abcd-0000-7000-8000-000000000060";
const BASE = `/api/bff/letting/listings/${LISTING_ID}/images`;

function image(n: number): ListingImage {
  return {
    document_id: `0192abcd-0000-7000-8000-00000000010${n}`,
    link_id: `0192abcd-0000-7000-8000-00000000020${n}`,
    title: `bild-${n}.png`,
    filename: `bild-${n}.png`,
    mime_type: "image/png",
    size: 24,
    created_at: "2026-09-26T08:00:00Z",
    linked_at: "2026-09-26T08:00:00Z",
    role: "attachment",
  };
}

describe("ListingImages", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists the linked images in link order with their position", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([image(1), image(2)]));
    renderIntl(<ListingImages listingId={LISTING_ID} />);
    const list = await screen.findByTestId("listing-image-list");
    const items = list.querySelectorAll("li");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Position 1");
    expect(items[0]?.querySelector("img")).toHaveAttribute("src", `${BASE}/${image(1).document_id}/content`);
    expect(items[1]).toHaveTextContent("bild-2.png");
  });

  it("uploads a file as multipart and shows the returned list", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse([image(1)], 201));
    renderIntl(<ListingImages listingId={LISTING_ID} />);
    expect(await screen.findByText("Noch keine Bilder verknüpft.")).toBeInTheDocument();
    const file = new File([new Uint8Array([137, 80, 78, 71])], "aussen.png", { type: "image/png" });
    await userEvent.upload(screen.getByTestId("listing-image-file"), file);
    await screen.findByTestId("listing-image-list");
    const upload = fetchMock.mock.calls.find((c) => c[1]?.method === "POST");
    expect(upload?.[0]).toBe(BASE);
    expect(upload?.[1]?.body).toBeInstanceOf(FormData);
    expect(screen.getByText("bild-1.png")).toBeInTheDocument();
  });

  it("links an existing document and unlinks after confirmation", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([image(1)]))
      .mockResolvedValueOnce(jsonResponse([image(1), image(2)], 201))
      .mockResolvedValueOnce(jsonResponse([image(2)]));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderIntl(<ListingImages listingId={LISTING_ID} />);
    await screen.findByTestId("listing-image-list");
    await userEvent.type(screen.getByTestId("listing-image-document-id"), image(2).document_id);
    await userEvent.click(screen.getByRole("button", { name: "Verknüpfen" }));
    await waitFor(() => expect(screen.getAllByText("Entfernen")).toHaveLength(2));
    const link = fetchMock.mock.calls[1];
    expect(link?.[0]).toBe(`${BASE}/link`);
    expect(JSON.parse(link?.[1]?.body as string)).toEqual({ document_id: image(2).document_id });

    await userEvent.click(screen.getAllByText("Entfernen")[0]!);
    await waitFor(() => expect(screen.getAllByText("Entfernen")).toHaveLength(1));
    expect(fetchMock.mock.calls[2]?.[0]).toBe(`${BASE}/${image(1).document_id}`);
    expect(fetchMock.mock.calls[2]?.[1]?.method).toBe("DELETE");
  });

  it("shows the API problem message", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Nicht gefunden", detail: "Anzeige fehlt." }, 404));
    renderIntl(<ListingImages listingId={LISTING_ID} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Anzeige fehlt.");
  });
});
