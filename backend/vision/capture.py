"""
ScreenCaptureService (spec section 12).

Uses `mss` for fast, cross-platform screen capture. Screenshots are only
ever taken when a tool explicitly requests it (this file has no background
timer or continuous capture loop) — per spec: "Do not send screenshots
unnecessarily."
"""

import base64
import io


class ScreenCaptureService:
    def capture_screen(self) -> bytes:
        """Full primary-monitor screenshot, returned as PNG bytes."""
        import mss
        from PIL import Image
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # index 0 is "all monitors combined"
            shot = sct.grab(monitor)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def capture_region(self, x: int, y: int, width: int, height: int) -> bytes:
        import mss
        from PIL import Image
        with mss.mss() as sct:
            region = {"left": x, "top": y, "width": width, "height": height}
            shot = sct.grab(region)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def capture_window(self, title_substring: str) -> bytes:
        import pygetwindow as gw
        matches = [w for w in gw.getAllWindows() if title_substring.lower() in w.title.lower()]
        if not matches:
            raise ValueError(f"No open window matches '{title_substring}'")
        win = matches[0]
        return self.capture_region(win.left, win.top, win.width, win.height)

    @staticmethod
    def to_base64(png_bytes: bytes) -> str:
        return base64.b64encode(png_bytes).decode("ascii")


screen_capture_service = ScreenCaptureService()
