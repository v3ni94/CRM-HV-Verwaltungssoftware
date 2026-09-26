/**
 * `getMe` must be built on React `cache()` so that layout and page share one `auth/me`
 * round trip per request. Outside a React server render `cache()` is a plain pass-through,
 * so the test installs a memoising `cache` and counts the calls on the API client.
 */
const calls = { get: 0, cache: 0 };

vi.mock("react", async () => {
  const actual = await vi.importActual<typeof import("react")>("react");
  return {
    ...actual,
    cache: <T extends (...args: never[]) => unknown>(fn: T): T => {
      calls.cache += 1;
      let memo: { value: unknown } | null = null;
      return ((...args: never[]) => {
        if (!memo) memo = { value: fn(...args) };
        return memo.value;
      }) as T;
    },
  };
});

vi.mock("@/lib/api-server", () => ({
  serverApi: () => ({
    GET: (path: string) => {
      calls.get += 1;
      return Promise.resolve({ data: { path, permissions: ["tickets:read"] }, error: undefined, response: new Response(null) });
    },
  }),
}));

describe("getMe", () => {
  it("is wrapped in React cache() and calls auth/me once per request", async () => {
    const { getMe } = await import("./me");
    expect(calls.cache).toBe(1);
    const [first, second] = await Promise.all([getMe(), getMe()]);
    const third = await getMe();
    expect(calls.get).toBe(1);
    expect(first).toBe(second);
    expect(third).toBe(first);
    expect(first.data).toMatchObject({ path: "/api/v1/auth/me", permissions: ["tickets:read"] });
  });
});
