/**
 * Preload script — the ONLY bridge between the sandboxed renderer (React
 * app) and Node/OS APIs. contextIsolation is on and nodeIntegration is off
 * in main.ts, so the renderer can never reach fs/child_process/etc directly.
 *
 * Nothing is exposed yet in Phase 1 (the renderer talks to the Python
 * backend over HTTP/WebSocket, not through Electron). This file exists now
 * so Phase 4 (computer control) has an established, reviewed pattern to
 * extend — e.g. contextBridge.exposeInMainWorld("solutionAI", { ... }) —
 * rather than introducing direct Node access under time pressure later.
 */

import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("solutionAI", {
  version: "0.1.0",
});
