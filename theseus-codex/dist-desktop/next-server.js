"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.findFreePort = findFreePort;
exports.startNextServer = startNextServer;
exports.stopNextServer = stopNextServer;
const child_process_1 = require("child_process");
const path_1 = __importDefault(require("path"));
const electron_1 = require("electron");
const net_1 = __importDefault(require("net"));
let serverProcess = null;
async function findFreePort(startPort = 3000) {
    const maxPort = 65535;
    for (let port = startPort; port <= maxPort; port++) {
        const free = await isPortFree(port);
        if (free)
            return port;
    }
    throw new Error(`No free port available starting from ${startPort}`);
}
function isPortFree(port) {
    return new Promise((resolve) => {
        const server = net_1.default.createServer();
        server.once("error", () => resolve(false));
        server.once("listening", () => {
            server.close(() => resolve(true));
        });
        server.listen(port, "127.0.0.1");
    });
}
async function waitForServer(port, timeoutMs) {
    const deadline = Date.now() + timeoutMs;
    let delay = 100;
    while (Date.now() < deadline) {
        const reachable = await canConnect(port);
        if (reachable)
            return;
        await sleep(delay);
        delay = Math.min(delay * 2, 2000);
    }
    throw new Error(`Next.js server did not become ready within ${timeoutMs}ms`);
}
function canConnect(port) {
    return new Promise((resolve) => {
        const socket = net_1.default.connect({ host: "127.0.0.1", port });
        const onDone = (ok) => {
            socket.removeAllListeners();
            socket.destroy();
            resolve(ok);
        };
        socket.once("connect", () => onDone(true));
        socket.once("error", () => onDone(false));
        socket.setTimeout(1000, () => onDone(false));
    });
}
function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}
async function startNextServer(dbUrl) {
    if (serverProcess) {
        throw new Error("Next.js server already running");
    }
    const port = await findFreePort(3000);
    const standaloneDir = path_1.default.join(electron_1.app.getAppPath(), ".next", "standalone");
    const serverScript = path_1.default.join(standaloneDir, "server.js");
    serverProcess = (0, child_process_1.fork)(serverScript, [], {
        cwd: standaloneDir,
        env: {
            ...process.env,
            PORT: String(port),
            HOSTNAME: "127.0.0.1",
            DATABASE_URL: dbUrl,
            NODE_ENV: "production",
        },
        stdio: "pipe",
    });
    serverProcess.stdout?.on("data", (chunk) => {
        process.stdout.write(`[next] ${chunk}`);
    });
    serverProcess.stderr?.on("data", (chunk) => {
        process.stderr.write(`[next] ${chunk}`);
    });
    serverProcess.on("exit", (code, signal) => {
        console.error(`[next] server exited code=${code} signal=${signal}`);
        serverProcess = null;
    });
    await waitForServer(port, 30_000);
    return port;
}
function stopNextServer() {
    if (!serverProcess)
        return;
    const proc = serverProcess;
    serverProcess = null;
    try {
        proc.kill("SIGTERM");
    }
    catch {
        // already dead
    }
    const killTimer = setTimeout(() => {
        try {
            proc.kill("SIGKILL");
        }
        catch {
            // already dead
        }
    }, 5000);
    proc.once("exit", () => clearTimeout(killTimer));
}
