import { render, screen } from "@testing-library/react";

import de from "../../messages/de.json";

import { ApiStatusLine } from "./ApiStatusLine";

const get = vi.fn();

vi.mock("@mhvp/api-client", () => ({
  createApiClient: () => ({ GET: get }),
}));

vi.mock("next-intl/server", () => ({
  getTranslations: async () => (key: keyof typeof de.Home) => de.Home[key],
}));

describe("ApiStatusLine", () => {
  beforeEach(() => {
    get.mockReset();
    process.env.MHVP_API_INTERNAL_URL = "http://api.test";
  });

  it("shows 'API bereit' when the API is ready", async () => {
    get.mockResolvedValue({ data: { status: "ok" }, response: new Response(null, { status: 200 }) });
    render(await ApiStatusLine());
    expect(screen.getByRole("status")).toHaveTextContent("API bereit");
  });

  it("shows 'API nicht erreichbar' on 503", async () => {
    get.mockResolvedValue({ error: { status: "fail" }, response: new Response(null, { status: 503 }) });
    render(await ApiStatusLine());
    expect(screen.getByRole("status")).toHaveTextContent("API nicht erreichbar");
  });

  it("shows 'API nicht erreichbar' when the request fails", async () => {
    get.mockRejectedValue(new TypeError("fetch failed"));
    render(await ApiStatusLine());
    expect(screen.getByRole("status")).toHaveTextContent("API nicht erreichbar");
  });
});
