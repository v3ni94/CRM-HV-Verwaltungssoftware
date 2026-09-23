import { createApiClient } from "./index";

describe("createApiClient", () => {
  it("calls the readiness endpoint and returns typed data", async () => {
    const fetchMock = vi.fn(async (request: Request) => {
      expect(request.url).toBe("http://api.test/api/v1/health/ready");
      return Response.json({ status: "ok", service: "api", version: "0.1.0", checks: {} });
    });
    const client = createApiClient("http://api.test/", fetchMock as unknown as typeof fetch);
    const { data, error } = await client.GET("/api/v1/health/ready");
    expect(error).toBeUndefined();
    expect(data?.status).toBe("ok");
  });

  it("exposes a 503 report as error", async () => {
    const fetchMock = vi.fn(async () =>
      Response.json({ status: "fail", service: "api", version: "0.1.0", checks: {} }, { status: 503 }),
    );
    const client = createApiClient("http://api.test", fetchMock as unknown as typeof fetch);
    const { data, error, response } = await client.GET("/api/v1/health/ready");
    expect(data).toBeUndefined();
    expect(response.status).toBe(503);
    expect(error?.status).toBe("fail");
  });
});
