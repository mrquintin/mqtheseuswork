"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const child_process_1 = require("child_process");
const net_1 = __importDefault(require("net"));
const path_1 = __importDefault(require("path"));
const DEV_PORT = 3000;
const DEV_HOST = "127.0.0.1";
const READY_TIMEOUT_MS = 60_000;
const projectRoot = path_1.default.resolve(__dirname, "..");
function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}
function canConnect(host, port) {
    return new Promise((resolve) => {
        const socket = net_1.default.connect({ host, port });
        const done = (ok) => {
            socket.removeAllListeners();
            socket.destroy();
            resolve(ok);
        };
        socket.once("connect", () => done(true));
        socket.once("error", () => done(false));
        socket.setTimeout(1000, () => done(false));
    });
}
async function waitForDevServer() {
    const deadline = Date.now() + READY_TIMEOUT_MS;
    let delay = 200;
    while (Date.now() < deadline) {
        if (await canConnect(DEV_HOST, DEV_PORT))
            return;
        await sleep(delay);
        delay = Math.min(delay * 1.5, 2000);
    }
    throw new Error(`Dev server did not start within ${READY_TIMEOUT_MS}ms`);
}
function spawnLocal(cmd, args, label) {
    const proc = (0, child_process_1.spawn)(cmd, args, {
        cwd: projectRoot,
        env: { ...process.env, PORT: String(DEV_PORT), HOSTNAME: DEV_HOST },
        stdio: ["ignore", "pipe", "pipe"],
        shell: false,
    });
    proc.stdout?.on("data", (c) => process.stdout.write(`[${label}] ${c}`));
    proc.stderr?.on("data", (c) => process.stderr.write(`[${label}] ${c}`));
    return proc;
}
async function main() {
    const npxCmd = process.platform === "win32" ? "npx.cmd" : "npx";
    const nextDev = spawnLocal(npxCmd, ["next", "dev", "-p", String(DEV_PORT), "-H", DEV_HOST], "next");
    let shuttingDown = false;
    const shutdown = (code) => {
        if (shuttingDown)
            return;
        shuttingDown = true;
        try {
            nextDev.kill("SIGTERM");
        }
        catch {
            // already dead
        }
        setTimeout(() => process.exit(code), 500);
    };
    nextDev.on("exit", (code) => {
        console.error(`[next] dev server exited code=${code}`);
        shutdown(code ?? 1);
    });
    try {
        await waitForDevServer();
    }
    catch (err) {
        console.error("[dev] failed waiting for Next.js:", err);
        shutdown(1);
        return;
    }
    const electronBin = require("electron");
    const electron = (0, child_process_1.spawn)(electronBin, [projectRoot], {
        cwd: projectRoot,
        env: { ...process.env, ELECTRON_DEV_URL: `http://${DEV_HOST}:${DEV_PORT}` },
        stdio: "inherit",
    });
    electron.on("exit", (code) => {
        shutdown(code ?? 0);
    });
    process.on("SIGINT", () => shutdown(0));
    process.on("SIGTERM", () => shutdown(0));
}
main().catch((err) => {
    console.error("[dev] fatal:", err);
    process.exit(1);
});
