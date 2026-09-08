import { expect, test } from "@playwright/test";

test("register, create an application, and show it on the board", async ({ page }) => {
  const email = `e2e-${Date.now()}@example.com`;
  await page.goto("/");
  await page.getByRole("button", { name: "免费创建" }).click();
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel("密码").fill("playwright-password-123");
  await page.getByRole("button", { name: /创建账户/ }).click();
  await expect(page.getByRole("heading", { name: "投递看板" })).toBeVisible();

  await page.getByRole("button", { name: /简历版本/ }).click();
  await page.getByLabel("版本名称 *").fill("E2E Resume");
  await page.getByLabel("简历文件").setInputFiles({
    name: "resume.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.7\n%%EOF"),
  });
  await page.getByRole("button", { name: "添加版本" }).click();
  await expect(page.getByText("E2E Resume", { exact: true })).toBeVisible();
  await expect(page.getByText("无法连接后端，请确认 API 已启动")).toHaveCount(0);
  await page.getByRole("button", { name: "取消" }).click();

  await page.getByRole("button", { name: /新建投递/ }).click();
  await page.getByLabel("公司名称 *").fill("Playwright Labs");
  await page.getByLabel("岗位名称 *").fill("Quality Engineer");
  await page.getByLabel("地点").fill("Remote");
  await page.getByRole("button", { name: "保存到待投递" }).click();

  await expect(page.getByText("Quality Engineer", { exact: true })).toBeVisible();
  await expect(page.getByText("Playwright Labs", { exact: true })).toBeVisible();

  await page.evaluate(async () => {
    const token = localStorage.getItem("jobflow_access_token");
    await fetch("http://127.0.0.1:8000/api/v1/auth/account", {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
  });
});
