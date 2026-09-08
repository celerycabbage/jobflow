import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, authenticate, clearToken, hasToken } from "./api";

function mockResponse(body: unknown, init: ResponseInit = {}) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(body === undefined ? null : JSON.stringify(body), {
      headers: { "Content-Type": "application/json" },
      ...init,
    }),
  );
}

describe("API client", () => {
  afterEach(() => {
    clearToken();
  });

  it("stores an access token after authentication", async () => {
    const fetchMock = mockResponse({ access_token: "test-token" }, { status: 201 });

    await authenticate("register", "qa@example.com", "password123");

    expect(hasToken()).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/auth/register"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("supports empty 204 responses", async () => {
    mockResponse(undefined, { status: 204 });
    await expect(api.deleteResume(3)).resolves.toBeUndefined();
  });

  it("returns the API detail for failed requests", async () => {
    mockResponse({ detail: "Resume version already exists" }, { status: 409 });
    await expect(api.createResume({ name: "v1" })).rejects.toMatchObject({
      message: "Resume version already exists",
      status: 409,
    } satisfies Partial<ApiError>);
  });
});
