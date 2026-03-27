import path from "node:path";
import dotenv from "dotenv";
import { GlobalBrowserTs } from "./browserManager.js";
import { getAbsPath, loadBbsConfig } from "./config.js";
import { login } from "./login.js";
import { tsLogger } from "./logger.js";
import {
  collectAllBoards,
  readJson,
  sanitizeDir,
  writeJson,
  type BoardNode,
} from "./init-utils.js";

type InitConfig = {
  board_pinned_concurrency?: number;
  board_article_concurrency?: number;
};

type PinnedItem = {
  title: string;
  url: string;
  time: string;
  author: string;
};

type Floor = {
  floor_name: string;
  author: string;
  author_id: string;
  nickname: string;
  time: string;
  content: string;
  like_count: number;
  dislike_count: number;
  level: string;
  article_count: string;
  score: string;
  constellation: string;
};

function normalizeBaseUrl(v: unknown): string {
  return String(v ?? "").trim().replace(/\/+$/, "");
}

function env(name: string): string {
  return String(process.env[name] ?? "").trim();
}

async function crawlBoardPinned(
  browser: GlobalBrowserTs,
  baseUrl: string,
  boardId: string
): Promise<PinnedItem[]> {
  const page = await browser.newPage(`${baseUrl}/#!board/${boardId}`, "domcontentloaded", 30_000);
  try {
    await page.waitForSelector("table tbody tr", { timeout: 15_000 });
    const rows = await page.$$eval("tr.top", (trs) =>
      trs.map((tr) => {
        const titleA =
          (tr.querySelector("td.title_9 a[href^='/article/']") as HTMLAnchorElement | null) ??
          (tr.querySelector("a[href^='/article/']") as HTMLAnchorElement | null);
        const dateCell = tr.querySelector("td.title_10");
        const authorA = tr.querySelector("td.title_12 a");
        return {
          title: (titleA?.textContent ?? "").trim(),
          url: ((titleA?.getAttribute("href") ?? "").trim() || "").split("?")[0],
          time: (dateCell?.textContent ?? "").trim(),
          author: (authorA?.textContent ?? "").trim(),
        };
      })
    );
    return rows.filter((r) => !!r.url);
  } finally {
    await page.close();
  }
}

async function crawlArticleDetail(
  browser: GlobalBrowserTs,
  baseUrl: string,
  articleUrl: string
): Promise<Floor[]> {
  const fullUrl = articleUrl.startsWith("http") ? articleUrl : `${baseUrl}${articleUrl}`;
  const page = await browser.newPage(fullUrl, "domcontentloaded", 30_000);
  try {
    await page.waitForSelector("div.b-content .a-wrap.corner, div.a-wrap.corner", {
      timeout: 15_000,
      state: "attached",
    });
    return await page.$$eval("div.b-content .a-wrap.corner, div.a-wrap.corner", (wraps) => {
      const floors: Floor[] = [];
      const timeRegex = /发信站:\s*[^(]+\(([^)]+)\)/;
      const likeRegex = /赞\((\d+)\)|楼主好评\s*\(\+?(\d+)\)/;
      const caiRegex = /踩\((\d+)\)|楼主差评\s*\(\+?(\d+)\)/;
      for (const wrap of wraps) {
        const head = wrap.querySelector("tr.a-head");
        const body = wrap.querySelector("tr.a-body");
        const bottom = wrap.querySelector("tr.a-bottom");

        const authorA = head?.querySelector(".a-u-name a") as HTMLAnchorElement | null;
        const author = (authorA?.textContent ?? "").trim();
        const href = (authorA?.getAttribute("href") ?? "").trim();
        const authorId = href.includes("/user/query/") ? href.split("/user/query/").pop()?.split("?")[0] ?? author : author;
        const floorName = (head?.querySelector(".a-pos")?.textContent ?? "").trim();

        const likeSource = (head?.textContent ?? "") + "\n" + (bottom?.textContent ?? "");
        const likeMatch = likeSource.match(likeRegex);
        const dislikeMatch = likeSource.match(caiRegex);
        const likeCount = Number(likeMatch?.[1] ?? likeMatch?.[2] ?? 0);
        const dislikeCount = Number(dislikeMatch?.[1] ?? dislikeMatch?.[2] ?? 0);

        const nickname = (body?.querySelector(".a-u-uid")?.textContent ?? "").trim();
        const contentWrap = body?.querySelector(".a-content-wrap");
        const content = (contentWrap?.textContent ?? "").trim();
        const timeMatch = (contentWrap?.textContent ?? "").match(timeRegex);
        const postTime = (timeMatch?.[1] ?? "").trim();

        const labels = Array.from(body?.querySelectorAll("dl.a-u-info dt") ?? []).map((n) =>
          (n.textContent ?? "").trim()
        );
        const values = Array.from(body?.querySelectorAll("dl.a-u-info dd") ?? []).map((n) =>
          (n.textContent ?? "").trim()
        );
        const kv = new Map<string, string>();
        labels.forEach((k, i) => kv.set(k, values[i] ?? ""));

        floors.push({
          floor_name: floorName,
          author,
          author_id: authorId,
          nickname,
          time: postTime,
          content,
          like_count: likeCount,
          dislike_count: dislikeCount,
          level: kv.get("等级") ?? "",
          article_count: kv.get("文章") ?? "",
          score: kv.get("积分") ?? "",
          constellation: kv.get("星座") ?? "",
        });
      }
      return floors;
    });
  } finally {
    await page.close();
  }
}

function buildIntro(pinned: PinnedItem, floors: Floor[]) {
  const first = floors[0] ?? ({} as Floor);
  return {
    title: pinned.title || "",
    time: first.time || pinned.time || "",
    author: first.author || pinned.author || "",
    reply_count: Math.max(0, floors.length - 1),
    url: pinned.url || "",
    floors,
  };
}

async function main(): Promise<void> {
  dotenv.config({ path: getAbsPath(".env") });
  const bbsConfig = await loadBbsConfig();
  const baseUrl = normalizeBaseUrl(bbsConfig.BBS_Url);
  if (!baseUrl) throw new Error("BBS_Url is missing in config/websites/bbs.json");

  const initConfig = await readJson<InitConfig>(getAbsPath("config/init.json"), {});
  const pinnedConcurrency = Math.max(1, Number(initConfig.board_pinned_concurrency ?? 32));
  const articleConcurrency = Math.max(1, Number(initConfig.board_article_concurrency ?? 64));

  const structure = await readJson<{ sections: BoardNode[] }>(getAbsPath("data/web_structure/forum_structure.json"), {
    sections: [],
  });
  if (!structure.sections.length) throw new Error("forum_structure.json missing or empty");

  const allBoards: Array<{ sectionName: string; pathParts: string[]; board: BoardNode }> = [];
  for (const sec of structure.sections) {
    allBoards.push(...collectAllBoards(sec, sec.name || "", []));
  }
  if (allBoards.length === 0) {
    throw new Error("board-init found 0 boards from forum_structure.json");
  }

  const browser = GlobalBrowserTs.getInstance({ headless: true });
  await browser.start();
  try {
    const username = env("BBS_Name");
    const password = env("BBS_Password");
    if (username && password) {
      await login(browser, username, password);
    } else {
      tsLogger.warn("board-init", "[board-init-ts] BBS_Name/BBS_Password missing, continue without login");
    }

    const pinnedResults: Array<{ dirPath: string; pinned: PinnedItem[] }> = [];
    const pinnedRunning = new Set<Promise<void>>();
    let pinnedDone = 0;
    let pinnedFailed = 0;
    const totalBoards = allBoards.length;
    tsLogger.info("board-init", `[board-init-ts] pinned stage start: total boards=${totalBoards}`);

    for (const item of allBoards) {
      let task: Promise<void>;
      task = (async () => {
        try {
          const pinned = await crawlBoardPinned(browser, baseUrl, item.board.id);
          const parts = [...item.pathParts.map(sanitizeDir), sanitizeDir(item.board.name || item.board.id)];
          const dirPath = path.join(getAbsPath("data/web_structure"), ...parts);
          pinnedResults.push({ dirPath, pinned });
        } catch (err) {
          pinnedFailed += 1;
          tsLogger.warn(
            "board-init",
            `[board-init-ts] pinned failed board=${item.board.id} name=${item.board.name || item.board.id} err=${String(err)}`
          );
        } finally {
          pinnedDone += 1;
          if (pinnedDone % 10 === 0 || pinnedDone === totalBoards) {
            tsLogger.info(
              "board-init",
              `[board-init-ts] pinned progress: ${pinnedDone}/${totalBoards}, failed=${pinnedFailed}`
            );
          }
        }
      })().finally(() => pinnedRunning.delete(task));
      pinnedRunning.add(task);
      if (pinnedRunning.size >= pinnedConcurrency) await Promise.race(pinnedRunning);
    }
    await Promise.all(pinnedRunning);
    const totalPinnedPosts = pinnedResults.reduce((acc, x) => acc + x.pinned.length, 0);
    tsLogger.info(
      "board-init",
      `[board-init-ts] pinned stage done: boards-ok=${pinnedResults.length}, boards-failed=${pinnedFailed}, pinned-posts=${totalPinnedPosts}`
    );

    const articleTasks: Array<Promise<void>> = [];
    const articleRunning = new Set<Promise<void>>();
    let articleDone = 0;
    let articleFailed = 0;
    const totalArticles = totalPinnedPosts;
    tsLogger.info("board-init", `[board-init-ts] article stage start: total articles=${totalArticles}`);

    for (const { dirPath, pinned } of pinnedResults) {
      for (let index = 0; index < pinned.length; index += 1) {
        const pinnedItem = pinned[index];
        let t: Promise<void>;
        t = (async () => {
          try {
            const floors = await crawlArticleDetail(browser, baseUrl, pinnedItem.url);
            const intro = buildIntro(pinnedItem, floors);
            await writeJson(path.join(dirPath, `介绍${index}.json`), intro);
          } catch (err) {
            articleFailed += 1;
            tsLogger.warn("board-init", `[board-init-ts] article failed err=${String(err)}`);
          } finally {
            articleDone += 1;
            if (articleDone % 10 === 0 || articleDone === totalArticles) {
              tsLogger.info(
                "board-init",
                `[board-init-ts] article progress: ${articleDone}/${totalArticles}, failed=${articleFailed}`
              );
            }
          }
        })().finally(() => articleRunning.delete(t));
        articleTasks.push(t);
        articleRunning.add(t);
        if (articleRunning.size >= articleConcurrency) await Promise.race(articleRunning);
      }
    }
    await Promise.all(articleTasks);
    tsLogger.info(
      "board-init",
      `[board-init-ts] article stage done: done=${articleDone}, failed=${articleFailed}`
    );
    tsLogger.info(
      "board-init",
      `[board-init-ts] boards: ${allBoards.length}, pinned-concurrency: ${pinnedConcurrency}, article-concurrency: ${articleConcurrency}`
    );
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  tsLogger.error("board-init", "[board-init-ts] failed", err);
  process.exitCode = 1;
});
