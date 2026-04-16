"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const electron_1 = require("electron");
electron_1.contextBridge.exposeInMainWorld("electronAPI", {
    platform: process.platform,
    versions: {
        electron: process.versions.electron,
        node: process.versions.node,
        chrome: process.versions.chrome,
    },
    onDeepLink: (callback) => electron_1.ipcRenderer.on("deep-link", (_event, url) => callback(url)),
});
