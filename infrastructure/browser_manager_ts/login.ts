import type { Page } from "playwright";
import { loadBbsConfig, loadLoginStructureConfig } from "./config.js";
import { GlobalBrowserTs } from "./browserManager.js";

export async function login(
  browser: GlobalBrowserTs,
  username: string,
  password: string
): Promise<boolean> {
  const structure = await loadLoginStructureConfig();
  const bbsConfig = await loadBbsConfig();

  const bbsUrl = String(bbsConfig.BBS_Url ?? "").trim().replace(/\/+$/, "");
  const loginUrl = String(structure.login_page_url ?? "").trim() || bbsUrl;
  const usernameId = String(structure.username_input_id ?? "id").trim();
  const passwordId = String(structure.password_input_id ?? "pwd").trim();
  const buttonId = String(structure.login_button_id ?? "b_login").trim();

  const page = await browser.newPage(loginUrl, "domcontentloaded", 60_000);
  try {
    if (usernameId) {
      await page.locator(`#${usernameId}`).fill(username);
    }
    if (passwordId) {
      await page.locator(`#${passwordId}`).fill(password);
    }
    if (username && password && buttonId) {
      await clickLoginWithFallback(page, buttonId);
      return true;
    }
    return false;
  } finally {
    await page.close();
  }
}

async function clickLoginWithFallback(page: Page, buttonId: string): Promise<void> {
  try {
    await Promise.all([
      page.waitForNavigation({ waitUntil: "load", timeout: 15_000 }),
      page.locator(`#${buttonId}`).click(),
    ]);
  } catch {
    await page.waitForTimeout(2_000);
  }
}
