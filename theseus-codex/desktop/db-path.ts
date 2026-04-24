import { app } from "electron";
import path from "path";
import fs from "fs";

export function getDbPath(): string {
  const userDataDir = app.getPath("userData");
  const dbDir = path.join(userDataDir, "data");
  fs.mkdirSync(dbDir, { recursive: true });
  return path.join(dbDir, "founder-portal.db");
}

export function getDatabaseUrl(): string {
  return `file:${getDbPath()}`;
}
