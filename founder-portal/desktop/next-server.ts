import { ChildProcess, fork } from "child_process";
import path from "path";
import { app } from "electron";
import net from "net";

let serverProcess: ChildProcess | null = null;

export async function findFreePort(startPort: number = 3000): Promise<number> {
  const maxPort = 65535;
  for (let port = startPort; port <= maxPort; port++) {
    const free = await isPortFree(port);
    if (free) return port;
  }
  throw new Error(`No free port available starting from ${startPort}`);
}

function isPortFree(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once("error", () => resolve(false));
    server.once("listening", () => {
      server.close(() => resolve(true));
    });
    server.listen(port, "127.0.0.1");
  });
}

async function waitForServer(port: number, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let delay = 100;
  while (Date.now() < deadline) {
    const reachable = await canConnect(port);
    if (reachable) return;
    await sleep(delay);
    delay = Math.min(delay * 2, 2000);
  }
  throw new Error(`Next.js server did not become ready within ${timeoutMs}ms`);
}

function canConnect(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = net.connect({ host: "127.0.0.1", port });
    const onDone = (ok: boolean) => {
      socket.removeAllListeners();
      socket.destroy();
      resolve(ok);
    };
    socket.once("connect", () => onDone(true));
    socket.once("error", () => onDone(false));
    socket.setTimeout(1000, () => onDone(false));
  });
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function startNextServer(dbUrl: string): Promise<number> {
  if (serverProcess) {
    throw new Error("Next.js server already running");
  }
  const port = await findFreePort(3000);
  const standaloneDir = path.join(app.getAppPath(), ".next", "standalone");
  const serverScript = path.join(standaloneDir, "server.js");

  serverProcess = fork(serverScript, [], {
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

export function stopNextServer(): void {
  if (!serverProcess) return;
  const proc = serverProcess;
  serverProcess = null;

  try {
    proc.kill("SIGTERM");
  } catch {
    // already dead
  }

  const killTimer = setTimeout(() => {
    try {
      proc.kill("SIGKILL");
    } catch {
      // already dead
    }
  }, 5000);

  proc.once("exit", () => clearTimeout(killTimer));
}
