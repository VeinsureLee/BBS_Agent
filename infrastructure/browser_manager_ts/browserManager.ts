import {
  chromium,
  type Browser,
  type BrowserContext,
  type Page,
} from "playwright";
import { loadDriverConfig } from "./config.js";
import { tsLogger } from "./logger.js";

type ProxyConfig = {
  server: string;
  bypass?: string;
  username?: string;
  password?: string;
};

type BrowserManagerOptions = {
  headless?: boolean;
  proxy?: ProxyConfig;
  userAgent?: string;
  storageState?: string;
};

export class GlobalBrowserTs {
  private static instance: GlobalBrowserTs | null = null;

  private browser: Browser | null = null;
  private context: BrowserContext | null = null;

  private readonly headless: boolean;
  private readonly proxy?: ProxyConfig;
  private readonly userAgent?: string;
  private readonly storageState?: string;

  private startingPromise: Promise<void> | null = null;

  private constructor(options: BrowserManagerOptions = {}) {
    this.headless = options.headless ?? true;
    this.proxy = options.proxy;
    this.userAgent = options.userAgent;
    this.storageState = options.storageState;
  }

  static getInstance(options: BrowserManagerOptions = {}): GlobalBrowserTs {
    if (!GlobalBrowserTs.instance) {
      GlobalBrowserTs.instance = new GlobalBrowserTs(options);
    }
    return GlobalBrowserTs.instance;
  }

  async start(): Promise<void> {
    if (this.browser) return;
    if (this.startingPromise) return this.startingPromise;

    this.startingPromise = (async () => {
      tsLogger.info("browser_manager_ts", "[browser_manager_ts] starting browser");
      const driverConfig = await loadDriverConfig();
      const chromePath = String(driverConfig.Chrome_Path ?? "").trim();

      const launchOptions: Parameters<typeof chromium.launch>[0] = {
        headless: this.headless,
      };

      if (this.proxy) {
        launchOptions.proxy = this.proxy;
      }
      if (chromePath) {
        launchOptions.executablePath = chromePath;
      }

      this.browser = await chromium.launch(launchOptions);

      const contextOptions: Parameters<Browser["newContext"]>[0] = {};
      if (this.userAgent) contextOptions.userAgent = this.userAgent;
      if (this.storageState) contextOptions.storageState = this.storageState;
      this.context = await this.browser.newContext(contextOptions);
      tsLogger.info("browser_manager_ts", "[browser_manager_ts] browser started");
    })();

    try {
      await this.startingPromise;
    } finally {
      this.startingPromise = null;
    }
  }

  async close(): Promise<void> {
    if (this.context) await this.context.close();
    if (this.browser) await this.browser.close();

    this.context = null;
    this.browser = null;
    tsLogger.info("browser_manager_ts", "[browser_manager_ts] browser closed");
  }

  async newPage(
    url?: string,
    waitUntil: "load" | "domcontentloaded" | "networkidle" = "load",
    timeout?: number
  ): Promise<Page> {
    if (!this.browser || !this.context) {
      await this.start();
    }
    if (!this.context) throw new Error("Browser context is not initialized.");

    const page = await this.context.newPage();
    if (url) {
      await page.goto(url, {
        waitUntil,
        timeout,
      });
    }
    return page;
  }

  async crawlPageContent(
    url: string,
    options: {
      asText?: boolean;
      waitAfterMs?: number;
      waitUntil?: "load" | "domcontentloaded" | "networkidle";
    } = {}
  ): Promise<string> {
    const page = await this.newPage(url, options.waitUntil ?? "load");
    try {
      if (options.waitAfterMs && options.waitAfterMs > 0) {
        await page.waitForTimeout(options.waitAfterMs);
      }
      return options.asText ? await page.innerText("body") : await page.content();
    } finally {
      await page.close();
    }
  }
}
