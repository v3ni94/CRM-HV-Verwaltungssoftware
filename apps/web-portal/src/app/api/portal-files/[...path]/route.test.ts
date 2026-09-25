// @vitest-environment node
const serverFetch = vi.fn();
vi.mock("@/lib/api-server", () => ({
  serverFetch: (...args: unknown[]) => serverFetch(...args),
}));

import { GET } from "./route";

const ctx = (path: string) => ({ params: Promise.resolve({ path: path.split("/") }) });
const ID = "01920000-0000-7000-8000-00000000000a";

describe("portal files", () => {
  beforeEach(() => serverFetch.mockReset());

  it("relays photos and the PDF inline", async () => {
    serverFetch.mockResolvedValue(
      new Response("%PDF-1.4", {
        status: 200,
        headers: { "content-type": "application/pdf", "content-disposition": 'inline; filename="a.pdf"' },
      }),
    );
    const res = await GET(new Request("http://portal.localhost/x"), ctx(`portal/handover/${ID}/pdf`));
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("application/pdf");
    expect(res.headers.get("cache-control")).toBe("private, no-store");
    expect(serverFetch.mock.calls[0]![0]).toBe(`/api/v1/portal/handover/${ID}/pdf`);
    serverFetch.mockResolvedValue(new Response("png", { status: 200, headers: { "content-type": "image/png" } }));
    expect(
      (await GET(new Request("http://portal.localhost/x"), ctx(`portal/handover/${ID}/documents/${ID}/content`)))
        .status,
    ).toBe(200);
  });

  it("keeps everything else outside and hides upstream errors", async () => {
    expect((await GET(new Request("http://portal.localhost/x"), ctx(`documents/${ID}/content`))).status).toBe(404);
    expect((await GET(new Request("http://portal.localhost/x"), ctx(`handover/protocols/${ID}/pdf`))).status).toBe(404);
    expect(serverFetch).not.toHaveBeenCalled();
    serverFetch.mockResolvedValue(new Response("secret", { status: 403 }));
    const res = await GET(new Request("http://portal.localhost/x"), ctx(`portal/handover/${ID}/pdf`));
    expect(res.status).toBe(404);
    expect(await res.text()).not.toContain("secret");
  });
});
