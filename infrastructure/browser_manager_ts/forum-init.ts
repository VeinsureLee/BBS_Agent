import dotenv from "dotenv";
import { GlobalBrowserTs } from "./browserManager.js";
import { getAbsPath, loadBbsConfig } from "./config.js";
import { readJson, writeJson, type BoardNode } from "./init-utils.js";
import { login } from "./login.js";
import { tsLogger } from "./logger.js";

type InitConfig = {
  crawl_concurrency?: number;
};

async function loadInitConfig(): Promise<InitConfig> {
  return readJson<InitConfig>(getAbsPath("config/init.json"), {});
}

function normalizeBaseUrl(v: unknown): string {
  return String(v ?? "").trim().replace(/\/+$/, "");
}

function env(name: string): string {
  return String(process.env[name] ?? "").trim();
}

async function crawlSections(baseUrl: string, browser: GlobalBrowserTs): Promise<BoardNode[]> {
  const page = await browser.newPage(baseUrl, "domcontentloaded", 30_000);
  try {
    try {
      await page.waitForSelector("a:has-text('全部讨论区')", { timeout: 10_000 });
      const trigger = page.locator("a:has-text('全部讨论区')").first();
      await trigger.click({ timeout: 3_000 });
      await page.waitForSelector("ul.x-child li span.text a[href^='/section/']", {
        timeout: 8_000,
      });
    } catch {
      // Fallback below
    }
    await page.waitForTimeout(300);
    const sections = await page.evaluate(() => {
      const out: Array<{ id: string; name: string; href: string }> = [];
      const links = document.querySelectorAll("ul.x-child li span.text a[href^='/section/']");
      for (const a of Array.from(links)) {
        const href = (a.getAttribute("href") ?? "").trim();
        const name = (a.textContent ?? "").trim();
        if (!href) continue;
        const id = href.replace(/\/+$/, "").split("/").pop()?.split("?")[0] ?? "";
        if (!id) continue;
        out.push({ id, name: name || `讨论区${id}`, href });
      }
      return out;
    });
    if (sections.length > 0) {
      return sections.map((s) => ({
        ...s,
        url: `${baseUrl}/#!section/${s.id}`,
      }));
    }

    const fallback: BoardNode[] = [];
    for (let i = 0; i < 10; i += 1) {
      const sid = String(i);
      fallback.push({
        id: sid,
        name: `讨论区${sid}`,
        href: `/section/${sid}`,
        url: `${baseUrl}/#!section/${sid}`,
      });
    }
    return fallback;
  } finally {
    await page.close();
  }
}

async function crawlSectionBoards(
  browser: GlobalBrowserTs,
  baseUrl: string,
  sectionId: string
): Promise<{ boards: BoardNode[]; sub_sections: BoardNode[] }> {
  const url = `${baseUrl}/#!section/${sectionId}`;
  const page = await browser.newPage(url, "domcontentloaded", 30_000);
  try {
    try {
      await page.waitForSelector("table tbody tr td.title_1", { timeout: 15_000 });
    } catch {
      await page.waitForTimeout(1_200);
    }
    const rows = await page.$$eval("table tbody tr", (trs) =>
      trs.map((tr) => {
        const first = tr.querySelector("td.title_1 a[href]") as HTMLAnchorElement | null;
        const second = tr.querySelector("td.title_2");
        return {
          href: (first?.getAttribute("href") ?? "").trim(),
          name: (first?.textContent ?? "").trim(),
          secondText: (second?.textContent ?? "").trim(),
        };
      })
    );
    const boards: BoardNode[] = [];
    const subSections: BoardNode[] = [];
    for (const row of rows) {
      if (!row.href || row.href.includes("javascript:")) continue;
      const boardMatch = row.href.match(/\/board\/([^/#?\s]+)/);
      const sectionMatch = row.href.match(/\/section\/([^/#?\s]+)/);
      if (boardMatch) {
        const id = boardMatch[1];
        boards.push({
          id,
          name: row.name || id,
          href: row.href,
          url: `${baseUrl}/#!board/${id}`,
        });
      } else if (sectionMatch && row.secondText.includes("[二级目录]")) {
        const id = sectionMatch[1];
        subSections.push({
          id,
          name: row.name || id,
          href: row.href,
          url: `${baseUrl}/#!section/${id}`,
          boards: [],
          sub_sections: [],
        });
      }
    }

    for (const sub of subSections) {
      try {
        const subTree = await crawlSectionBoards(browser, baseUrl, sub.id);
        sub.boards = subTree.boards;
        sub.sub_sections = [];
      } catch {
        sub.boards = [];
        sub.sub_sections = [];
      }
    }
    return { boards, sub_sections: subSections };
  } finally {
    await page.close();
  }
}

async function main(): Promise<void> {
  dotenv.config({ path: getAbsPath(".env") });
  const bbsConfig = await loadBbsConfig();
  const baseUrl = normalizeBaseUrl(bbsConfig.BBS_Url);
  if (!baseUrl) {
    throw new Error("BBS_Url is missing in config/websites/bbs.json");
  }

  const initConfig = await loadInitConfig();
  const concurrency = Math.max(1, Number(initConfig.crawl_concurrency ?? 4));

  const browser = GlobalBrowserTs.getInstance({ headless: true });
  await browser.start();
  try {
    const username = env("BBS_Name");
    const password = env("BBS_Password");
    if (username && password) {
      await login(browser, username, password);
    } else {
      tsLogger.warn("forum-init", "[forum-init-ts] BBS_Name/BBS_Password missing, continue without login");
    }

    const sections = await crawlSections(baseUrl, browser);
    const sem: Array<Promise<BoardNode>> = [];
    const running = new Set<Promise<BoardNode>>();

    const launchOne = (sec: BoardNode): Promise<BoardNode> =>
      (async () => {
        const tree = await crawlSectionBoards(browser, baseUrl, sec.id);
        return {
          id: sec.id,
          name: sec.name,
          href: sec.href,
          url: sec.url,
          boards: tree.boards,
          sub_sections: tree.sub_sections,
        };
      })();

    for (const sec of sections) {
      const p = launchOne(sec).finally(() => running.delete(p));
      running.add(p);
      sem.push(p);
      if (running.size >= concurrency) {
        await Promise.race(running);
      }
    }

    const builtSections = await Promise.all(sem);
    const totalBoards = builtSections.reduce((acc, sec) => {
      const direct = sec.boards?.length ?? 0;
      const nested = (sec.sub_sections ?? []).reduce((n, sub) => n + (sub.boards?.length ?? 0), 0);
      return acc + direct + nested;
    }, 0);
    if (totalBoards <= 0) {
      throw new Error("forum-init produced 0 boards; SPA content likely not loaded");
    }
    await writeJson(getAbsPath("data/web_structure/forum_structure.json"), {
      sections: builtSections,
    });
    tsLogger.info("forum-init", `[forum-init-ts] sections saved: ${builtSections.length}, boards: ${totalBoards}`);
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  tsLogger.error("forum-init", "[forum-init-ts] failed", err);
  process.exitCode = 1;
});
