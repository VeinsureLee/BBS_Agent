import fs from "node:fs/promises";
import path from "node:path";
import { getAbsPath } from "./config.js";

type Level = "INFO" | "WARN" | "ERROR";

function dateStr(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}${m}${day}`;
}

function timeStr(d: Date): string {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}`;
}

async function writeLine(level: Level, scope: string, message: string): Promise<void> {
  const now = new Date();
  const line = `${timeStr(now)} - ${scope} - ${level} - ${message}\n`;
  const logPath = getAbsPath(`logs/ts/browser_manager_ts/browser_manager_ts_${dateStr(now)}.log`);
  await fs.mkdir(path.dirname(logPath), { recursive: true });
  await fs.appendFile(logPath, line, "utf-8");
}

function stringifyError(err: unknown): string {
  if (err instanceof Error) return `${err.name}: ${err.message}`;
  return String(err);
}

export const tsLogger = {
  info(scope: string, message: string): void {
    console.info(message);
    void writeLine("INFO", scope, message);
  },
  warn(scope: string, message: string): void {
    console.warn(message);
    void writeLine("WARN", scope, message);
  },
  error(scope: string, message: string, err?: unknown): void {
    const full = err ? `${message} | ${stringifyError(err)}` : message;
    console.error(full);
    void writeLine("ERROR", scope, full);
  },
};
