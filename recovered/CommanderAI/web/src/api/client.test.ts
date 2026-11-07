import { ApiError, unwrap } from "./client";

const response = (status: number) => new Response(null, { status, statusText: "x" });

describe("unwrap", () => {
  it("returns data for successful responses", async () => {
    await expect(
      unwrap(Promise.resolve({ data: { ok: 1 }, response: response(200) })),
    ).resolves.toEqual({ ok: 1 });
  });

  it("throws ApiError with the server's error body", async () => {
    const error = {
      error: { code: "deck_not_found", message: "Deck #9 not found", details: [], data: { id: 9 } },
    };
    const call = unwrap(Promise.resolve({ error, response: response(404) }));
    await expect(call).rejects.toBeInstanceOf(ApiError);
    await expect(call).rejects.toMatchObject({
      status: 404,
      code: "deck_not_found",
      message: "Deck #9 not found",
    });
  });

  it("wraps unexpected error bodies and network failures", async () => {
    await expect(
      unwrap(Promise.resolve({ error: "boom", response: response(500) })),
    ).rejects.toMatchObject({
      status: 500,
      code: "http_error",
    });
    await expect(unwrap(Promise.reject(new TypeError("Failed to fetch")))).rejects.toMatchObject({
      status: 0,
      code: "network_error",
    });
  });
});
