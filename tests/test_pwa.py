"""The app installs as a desktop/mobile app: manifest, icons, shell worker."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def test_manifest_is_complete_and_icons_exist():
    manifest = json.loads((WEB / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/"
    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert {"192x192", "512x512"} <= sizes
    assert any(icon.get("purpose") == "maskable" for icon in manifest["icons"])
    for name in ("icon-192.png", "icon-512.png"):
        data = (WEB / name).read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_page_wires_manifest_and_shell_worker():
    markup = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'rel="manifest"' in markup
    assert 'name="theme-color"' in markup
    assert 'rel="apple-touch-icon"' in markup

    script = (WEB / "app.js").read_text(encoding="utf-8")
    assert 'serviceWorker.register("/sw.js")' in script
    assert "beforeinstallprompt" in script

    worker = (WEB / "sw.js").read_text(encoding="utf-8")
    # Deploys must win when online; only the offline path may serve the cache,
    # and the fetch revalidates past the browser's heuristic HTTP cache.
    assert 'fetch(event.request.url, { cache: "no-cache"' in worker
    assert '.startsWith("/api/")' in worker
