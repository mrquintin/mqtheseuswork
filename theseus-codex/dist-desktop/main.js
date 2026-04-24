"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const electron_1 = require("electron");
const path_1 = __importDefault(require("path"));
const fs_1 = __importDefault(require("fs"));
const child_process_1 = require("child_process");
const db_path_1 = require("./db-path");
const next_server_1 = require("./next-server");
let mainWindow = null;
const gotLock = electron_1.app.requestSingleInstanceLock();
if (!gotLock) {
    electron_1.app.quit();
}
electron_1.app.on("second-instance", () => {
    if (mainWindow) {
        if (mainWindow.isMinimized())
            mainWindow.restore();
        mainWindow.focus();
    }
});
function runPrismaMigrations(dbUrl) {
    const appPath = electron_1.app.getAppPath();
    const schemaPath = path_1.default.join(appPath, "prisma", "schema.prisma");
    if (!fs_1.default.existsSync(schemaPath)) {
        console.warn(`[main] Prisma schema not found at ${schemaPath}; skipping migrate`);
        return;
    }
    const result = (0, child_process_1.spawnSync)(process.execPath, [path_1.default.join(appPath, "node_modules", "prisma", "build", "index.js"), "migrate", "deploy", "--schema", schemaPath], {
        env: { ...process.env, DATABASE_URL: dbUrl },
        stdio: "inherit",
    });
    if (result.status !== 0) {
        console.error(`[main] prisma migrate deploy exited with status ${result.status}`);
    }
}
async function createWindow(port) {
    mainWindow = new electron_1.BrowserWindow({
        width: 1400,
        height: 900,
        minWidth: 1024,
        minHeight: 700,
        titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
        webPreferences: {
            preload: path_1.default.join(__dirname, "preload.js"),
            contextIsolation: true,
            nodeIntegration: false,
        },
    });
    mainWindow.webContents.setWindowOpenHandler(({ url }) => {
        electron_1.shell.openExternal(url);
        return { action: "deny" };
    });
    mainWindow.webContents.on("will-navigate", (event, url) => {
        const target = new URL(url);
        const isLocal = target.hostname === "127.0.0.1" || target.hostname === "localhost";
        if (!isLocal) {
            event.preventDefault();
            electron_1.shell.openExternal(url);
        }
    });
    mainWindow.on("closed", () => {
        mainWindow = null;
    });
    await mainWindow.loadURL(`http://127.0.0.1:${port}`);
}
electron_1.app.whenReady().then(async () => {
    try {
        const dbUrl = (0, db_path_1.getDatabaseUrl)();
        const dbPath = (0, db_path_1.getDbPath)();
        const firstLaunch = !fs_1.default.existsSync(dbPath) || fs_1.default.statSync(dbPath).size === 0;
        if (firstLaunch) {
            runPrismaMigrations(dbUrl);
        }
        const port = await (0, next_server_1.startNextServer)(dbUrl);
        await createWindow(port);
    }
    catch (err) {
        console.error("[main] startup failed:", err);
        electron_1.app.quit();
    }
});
electron_1.app.on("window-all-closed", () => {
    electron_1.app.quit();
});
electron_1.app.on("before-quit", () => {
    (0, next_server_1.stopNextServer)();
});
