import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

type JsonRecord = Record<string, unknown>;

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export const projectRoot = path.resolve(__dirname, "..", "..");

async function loadJson(filePath: string): Promise<JsonRecord> {
  try {
    const raw = await fs.readFile(filePath, "utf-8");
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? (parsed as JsonRecord) : {};
  } catch {
    return {};
  }
}

export function getAbsPath(relativePath: string): string {
  return path.resolve(projectRoot, relativePath);
}

export async function loadBbsConfig(): Promise<JsonRecord> {
  return loadJson(getAbsPath("config/websites/bbs.json"));
}

export async function loadDriverConfig(): Promise<JsonRecord> {
  return loadJson(getAbsPath("config/driver/driver.json"));
}

export async function loadLoginStructureConfig(): Promise<JsonRecord> {
  return loadJson(getAbsPath("config/data/login_structure.json"));
}
