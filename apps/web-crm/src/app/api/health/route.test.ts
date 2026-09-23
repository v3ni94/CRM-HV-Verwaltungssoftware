// @vitest-environment node
import pkg from "../../../../package.json";

import { GET } from "./route";

describe("GET /api/health", () => {
  afterEach(() => {
    delete process.env.MHVP_APP_VERSION;
  });

  it("returns the contract JSON with the package version", async () => {
    const response = GET();
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ status: "ok", service: "web-crm", version: pkg.version });
  });

  it("prefers MHVP_APP_VERSION", async () => {
    process.env.MHVP_APP_VERSION = "9.9.9";
    expect(await GET().json()).toEqual({ status: "ok", service: "web-crm", version: "9.9.9" });
  });
});
