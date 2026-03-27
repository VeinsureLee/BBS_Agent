import fs from "node:fs/promises";
import path from "node:path";
import dotenv from "dotenv";
import { loadBbsConfig, getAbsPath } from "./config.js";
import { GlobalBrowserTs } from "./browserManager.js";
import { login } from "./login.js";

function env(name: string): string {
  return (process.env[name] ?? "").trim();
}

async function main(): Promise<void> {
  dotenv.config({ path: getAbsPath(".env") });

  const bbsConfig = await loadBbsConfig();
  const homeUrl = String(bbsConfig.BBS_Url ?? "").trim().replace(/\/+$/, "");
  if (!homeUrl) {
    console.error("BBS_Url is missing in config/websites/bbs.json");
    return;
  }

  const browser = GlobalBrowserTs.getInstance({ headless: true });
  await browser.start();
  try {
    const username = env("BBS_Name");
    const password = env("BBS_Password");
    if (username && password) {
      await login(browser, username, password);
    } else {
      console.warn("BBS_Name/BBS_Password not set in .env, skip login");
    }

    const forumHome = `${homeUrl}/#!board/BUPTDNF`;
    const html = await browser.crawlPageContent(forumHome, { waitAfterMs: 3000 });

    const outPath = getAbsPath("data/test/test_ts.html");
    await fs.mkdir(path.dirname(outPath), { recursive: true });
    await fs.writeFile(outPath, html, "utf-8");
    console.info(`[browser_manager_ts] page saved: ${outPath}`);
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error("[browser_manager_ts] unexpected error:", error);
  process.exitCode = 1;
});
