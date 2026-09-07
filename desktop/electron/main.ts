/**
 * Electron main process.
 *
 * Dev mode: opens a window pointing at the Vite dev server. The Python
 * backend is expected to already be running separately (per README.md) —
 * this keeps the fast-reload dev loop simple, with backend logs visible in
 * their own terminal instead of buried in Electron's.
 *
 * Packaged (production) mode: the backend is bundled as a standalone .exe
 * via PyInstaller (see package.json "build:backend") and placed in
 * `resources/backend/` by electron-builder's `extraResources`. This process
 * spawns it as a child process on startup and kills it on quit, so the
 * installed app is a single double-clickable thing with no separate
 * "start the backend" step for the end user.
 *
 * Computer-control IPC handlers (spec section 11-12) that need direct OS
 * access from the main process (as opposed to the Python backend's
 * pyautogui-based tools) can be added here via ipcMain.handle(...) and
 * exposed through preload.ts if a future phase needs them; none are needed
 * yet since backend/tools/computer_control.py already covers that surface.
 */

import { app, BrowserWindow } from "electron";
import { ChildProcess, spawn } from "node:child_process";
import path from "node:path";

const isDev = !app.isPackaged;
let backendProcess: ChildProcess | null = null;

function startBackend() {
  if (isDev) return; // dev: run `uvicorn backend.main:app --reload` yourself, see README.md
  const exePath = path.join(process.resourcesPath, "backend", "solution-ai-backend.exe");
  backendProcess = spawn(exePath, [], { stdio: "ignore" });
  backendProcess.on("error", (err) => {
    console.error("Failed to start bundled backend:", err);
  });
}

function stopBackend() {
  backendProcess?.kill();
  backendProcess = null;
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1200,
    height: 800,
    title: "Solution AI",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (isDev) {
    win.loadURL("http://localhost:5173");
    win.webContents.openDevTools({ mode: "detach" });
  } else {
    win.loadFile(path.join(__dirname, "../../frontend/dist/index.html"));
  }
}

app.whenReady().then(() => {
  startBackend();
  createWindow();
});

app.on("window-all-closed", () => {
  stopBackend();
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

app.on("before-quit", stopBackend);
