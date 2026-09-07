Place `icon.ico` (Windows icon, ideally 256x256) here before running `npm run dist`.
electron-builder's `win.icon` config points at this file. Without it, electron-builder
falls back to its own default icon — the build still succeeds, it just won't look
like Solution AI's branding until you add one.
