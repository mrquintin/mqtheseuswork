"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.getDbPath = getDbPath;
exports.getDatabaseUrl = getDatabaseUrl;
const electron_1 = require("electron");
const path_1 = __importDefault(require("path"));
const fs_1 = __importDefault(require("fs"));
function getDbPath() {
    const userDataDir = electron_1.app.getPath("userData");
    const dbDir = path_1.default.join(userDataDir, "data");
    fs_1.default.mkdirSync(dbDir, { recursive: true });
    return path_1.default.join(dbDir, "founder-portal.db");
}
function getDatabaseUrl() {
    return `file:${getDbPath()}`;
}
