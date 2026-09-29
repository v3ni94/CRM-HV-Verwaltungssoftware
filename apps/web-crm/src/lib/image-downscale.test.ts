import { downscale } from "./image-downscale";

function file(size = 8 * 1024 * 1024, name = "foto.heic", type = "image/heic"): File {
  const f = new File([new Uint8Array(16)], name, { type });
  Object.defineProperty(f, "size", { value: size });
  return f;
}

describe("downscale", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("returns the original without createImageBitmap", async () => {
    vi.stubGlobal("createImageBitmap", undefined);
    const input = file();
    expect(await downscale(input)).toBe(input);
  });

  it("returns the original when the browser cannot decode the file (HEIC without decoder)", async () => {
    vi.stubGlobal("createImageBitmap", vi.fn(async () => { throw new Error("decode"); }));
    const input = file();
    expect(await downscale(input)).toBe(input);
  });

  it("returns the original for a small image", async () => {
    vi.stubGlobal("createImageBitmap", vi.fn(async () => ({ width: 1200, height: 800, close: vi.fn() })));
    const input = file(500 * 1024, "klein.jpg", "image/jpeg");
    expect(await downscale(input)).toBe(input);
  });

  it("scales 4000x3000 to 2000x1500 and returns a JPEG", async () => {
    const close = vi.fn();
    vi.stubGlobal("createImageBitmap", vi.fn(async () => ({ width: 4000, height: 3000, close })));
    const drawImage = vi.fn();
    const canvas = {
      width: 0,
      height: 0,
      getContext: () => ({ drawImage }),
      toBlob: (cb: (b: Blob | null) => void, type: string) => cb(new Blob(["x"], { type })),
    };
    vi.spyOn(document, "createElement").mockReturnValue(canvas as unknown as HTMLCanvasElement);
    const out = await downscale(file());
    expect(canvas.width).toBe(2000);
    expect(canvas.height).toBe(1500);
    expect(drawImage).toHaveBeenCalledWith(expect.anything(), 0, 0, 2000, 1500);
    expect(out.type).toBe("image/jpeg");
    expect(out.name).toBe("foto.jpg");
    expect(close).toHaveBeenCalled();
  });
});
