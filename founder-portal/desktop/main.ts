import { app, BrowserWindow, shell } from "electron";
import path from "path";
import fs from "fs";
import { spawnSync } from "child_process";
import { getDatabaseUrl, getDbPath } from "./db-path";
import { startNextServer, stopNextServer } from "./next-server";
import { initAutoUpdater } from "./updater";

let mainWindow: BrowserWindow | null = null;

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
}

app.on("second-instance", () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});

function runPrismaMigrations(dbUrl: string): void {
  const appPath = app.getAppPath();
  const schemaPath = path.join(appPath, "prisma", "schema.prisma");
  if (!fs.existsSync(schemaPath)) {
    console.warn(`[main] Prisma schema not found at ${schemaPath}; skipping migrate`);
    return;
  }

  const result = spawnSync(
    process.execPath,
    [path.join(appPath, "node_modules", "prisma", "build", "index.js"), "migrate", "deploy", "--schema", schemaPath],
    {
      env: { ...process.env, DATABASE_URL: dbUrl },
      stdio: "inherit",
    },
  );

  if (result.status !== 0) {
    console.error(`[main] prisma migrate deploy exited with status ${result.status}`);
  }
}

async function createWindow(port: number): Promise<void> {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  mainWindow.webContents.on("will-navigate", (event, url) => {
    const target = new URL(url);
    const isLocal = target.hostname === "127.0.0.1" || target.hostname === "localhost";
    if (!isLocal) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  await mainWindow.loadURL(`http://127.0.0.1:${port}`);

  try {
    initAutoUpdater(mainWindow);
  } catch (e) {
    console.warn("Auto-updater not configured:", e);
  }
}

app.whenReady().then(async () => {
  try {
    const dbUrl = getDatabaseUrl();
    const dbPath = getDbPath();
    const firstLaunch = !fs.existsSync(dbPath) || fs.statSync(dbPath).size === 0;
    if (firstLaunch) {
      runPrismaMigrations(dbUrl);
    }

    const port = await startNextServer(dbUrl);
    await createWindow(port);
  } catch (err) {
    console.error("[main] startup failed:", err);
    app.quit();
  }
});

app.on("window-all-closed", () => {
  app.quit();
});

app.on("before-quit", () => {
  stopNextServer();
});
