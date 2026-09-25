// @vitest-environment node
const serverFetch = vi.fn();
vi.mock("@/lib/api-server", () => ({
  serverFetch: (...args: unknown[]) => serverFetch(...args),
}));

import { GET } from "./route";

const ctx = (path: string) => ({
  params: Promise.resolve({ path: path.split("/") }),
});
const ID = "01920000-0000-7000-8000-00000000000a";

describe("handover files", () => {
  beforeEach(() => serverFetch.mockReset());

  it("relays a protocol PDF inline with its content type", async () => {
    serverFetch.mockResolvedValue(
      new Response("%PDF-1.4", {
        status: 200,
        headers: {
          "content-type": "application/pdf",
          "content-disposition": 'inline; filename="a.pdf"',
        },
      }),
    );
    const res = await GET(
      new Request(
        `http://crm.localhost/api/handover-files/handover/protocols/${ID}/pdf?download=false`,
      ),
      ctx(`handover/protocols/${ID}/pdf`),
    );
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("application/pdf");
    expect(res.headers.get("content-disposition")).toContain("a.pdf");
    expect(serverFetch.mock.calls[0]![0]).toBe(
      `/api/v1/handover/protocols/${ID}/pdf?download=false`,
    );
  });

  it("serves document content and keeps everything else outside", async () => {
    serverFetch.mockResolvedValue(
      new Response("png", {
        status: 200,
        headers: { "content-type": "image/png" },
      }),
    );
    expect(
      (
        await GET(
          new Request("http://crm.localhost/x"),
          ctx(`documents/${ID}/content`),
        )
      ).status,
    ).toBe(200);
    expect(
      (await GET(new Request("http://crm.localhost/x"), ctx(`documents/${ID}`)))
        .status,
    ).toBe(404);
    expect(
      (await GET(new Request("http://crm.localhost/x"), ctx("contacts")))
        .status,
    ).toBe(404);
    expect(serverFetch).toHaveBeenCalledTimes(1);
  });

  it("maps upstream errors to 404 without leaking the body", async () => {
    serverFetch.mockResolvedValue(new Response("secret", { status: 403 }));
    const res = await GET(
      new Request("http://crm.localhost/x"),
      ctx(`documents/${ID}/content`),
    );
    expect(res.status).toBe(404);
    expect(await res.text()).not.toContain("secret");
  });
});
