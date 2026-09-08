import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthScreen } from "./AuthScreen";

describe("AuthScreen", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("authenticates and stores the access token", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ access_token: "token-from-api" }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    )));
    const authenticated = vi.fn();
    const user = userEvent.setup();
    render(<AuthScreen onAuthenticated={authenticated} />);

    await user.type(screen.getByLabelText("邮箱"), "owner@example.com");
    await user.type(screen.getByLabelText("密码"), "password123");
    await user.click(screen.getByRole("button", { name: /登录/ }));

    expect(authenticated).toHaveBeenCalledOnce();
    expect(localStorage.getItem("jobflow_access_token")).toBe("token-from-api");
  });

  it("shows the API error and allows retry", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "Invalid credentials" }),
      { status: 401, headers: { "Content-Type": "application/json" } },
    )));
    const user = userEvent.setup();
    render(<AuthScreen onAuthenticated={vi.fn()} />);

    await user.type(screen.getByLabelText("邮箱"), "owner@example.com");
    await user.type(screen.getByLabelText("密码"), "wrong-password");
    await user.click(screen.getByRole("button", { name: /登录/ }));

    expect(await screen.findByText("Invalid credentials")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /登录/ })).toBeEnabled();
  });
});
