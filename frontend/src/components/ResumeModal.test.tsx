import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ResumeModal } from "../App";
import { api } from "../api";

describe("ResumeModal", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("clears the form without reporting a connection error after an upload succeeds", async () => {
    const upload = vi.spyOn(api, "uploadResume").mockResolvedValue({
      id: 4,
      name: "后端实习 v1",
      file_name: "resume.pdf",
      has_file: true,
      created_at: "2026-09-08T00:00:00Z",
    });
    const onCreated = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<ResumeModal resumes={[]} onClose={vi.fn()} onCreated={onCreated} />);

    const nameInput = screen.getByLabelText("版本名称 *");
    const fileInput = screen.getByLabelText("简历文件") as HTMLInputElement;
    await user.type(nameInput, "后端实习 v1");
    await user.upload(fileInput, new File(["%PDF-1.7"], "resume.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: "添加版本" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledOnce());
    expect(upload).toHaveBeenCalledWith("后端实习 v1", expect.any(File));
    expect(nameInput).toHaveValue("");
    expect(screen.queryByText("无法连接后端，请确认 API 已启动")).not.toBeInTheDocument();
  });
});
