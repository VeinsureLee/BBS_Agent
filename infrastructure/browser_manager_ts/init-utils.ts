import fs from "node:fs/promises";
import path from "node:path";

export type BoardNode = {
  id: string;
  name: string;
  href?: string;
  url?: string;
  boards?: BoardNode[];
  sub_sections?: BoardNode[];
};

export function sanitizeDir(name: string): string {
  const value = (name ?? "").trim();
  if (!value) return "未分类";
  return value.replace(/[<>:"/\\|?*]/g, "_") || "未分类";
}

export async function readJson<T>(filePath: string, fallback: T): Promise<T> {
  try {
    const raw = await fs.readFile(filePath, "utf-8");
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export async function writeJson(filePath: string, data: unknown): Promise<void> {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, JSON.stringify(data, null, 2), "utf-8");
}

export function collectAllBoards(
  sectionNode: BoardNode,
  sectionName: string,
  pathPrefix: string[]
): Array<{ sectionName: string; pathParts: string[]; board: BoardNode }> {
  const out: Array<{ sectionName: string; pathParts: string[]; board: BoardNode }> = [];
  const name = sectionNode.name || "";
  const prefix = [...pathPrefix, name];
  for (const b of sectionNode.boards ?? []) {
    out.push({ sectionName, pathParts: prefix, board: b });
  }
  for (const sub of sectionNode.sub_sections ?? []) {
    out.push(...collectAllBoards(sub, sectionName, prefix));
  }
  return out;
}
