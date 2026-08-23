# Desktop build (Electron)

The desktop app is the same React SPA in an Electron shell, loading from
`file://` instead of a web server.

---

## Build

```bash
cd frontend

npm run electron:build:win        # Windows: installer + portable + zip
npm run electron:build:win:zip    # Windows: zip only (no Wine needed)
npm run electron:build:linux      # Linux AppImage
```

Output lands in `frontend/release/` (git-ignored).

### Cross-building from Linux or macOS needs Wine

electron-builder patches the `.exe` icon and version metadata with `rcedit`, and
builds the NSIS installer's uninstaller by running it — both are Windows binaries
that need Wine on a non-Windows host.

```bash
sudo pacman -S wine          # Arch
sudo apt install wine64      # Debian / Ubuntu
brew install --cask wine-stable
```

Without Wine, only the **zip** target builds:

```bash
npm run electron:build:win:zip
```

That produces a complete, working application — it just has no installer, and
the `.exe` keeps Electron's default icon and file properties, because that is the
step Wine performs. The installer's own icon is unaffected.

Building on Windows, or in CI on a `windows-latest` runner, needs none of this.

---

## Configuration

Edit **`frontend/.env.desktop`**:

```ini
VITE_DESKTOP_API_BASE_URL=https://api.dayflow.app/api
VITE_WS_URL=wss://api.dayflow.app/ws/updates/
```

These must be **absolute URLs**. The app loads from `file://`, so a relative
`/api` has nothing to resolve against. Vite inlines them at build time — changing
one means rebuilding.

> Everything in a `VITE_*` variable ships inside the bundle and is readable by
> anyone who installs the app. Never put a secret in this file.

### The backend must allow the desktop origin

A page loaded from `file://` has an opaque origin and sends `Origin: null`. The
API's CORS allowlist rejects that by default, so **the desktop app cannot reach
the API until you enable it**:

```ini
DJANGO_ALLOW_DESKTOP_ORIGIN=true
```

This is opt-in because it widens CORS to any locally-opened HTML file. Enable it
only if you actually ship the desktop build.

Symptom if you forget: the app opens, shows the login screen, and every request
fails with a CORS error in the console.

---

## What ships

| | |
|---|---|
| `DayFllow.exe` | Electron runtime |
| `resources/app.asar` | The app — ~1 MB |
| `*.dll`, `*.pak`, `icudtl.dat`, `locales/` | Chromium runtime |

`app.asar` excludes `node_modules` entirely. Vite bundles every runtime
dependency into `dist/`, so shipping the dependency tree added ~85 MB that
nothing ever required.

The zip is ~107 MB. Almost all of that is Chromium; there is no meaningful way to
reduce it.

---

## Security posture

`electron/main.cjs` runs with `contextIsolation: true`, `sandbox: true`,
`nodeIntegration: false` and `webSecurity: true`. The preload exposes four window
controls over `contextBridge` and nothing else — no filesystem, no shell, no
arbitrary IPC.

Two hardening changes from the audit:

- **DevTools no longer open in packaged builds** (V-31). They used to open on
  every launch of the shipped app. The View menu still has them.
- **External navigation is blocked**, and `https://` links open in the user's real
  browser via `shell.openExternal` rather than inside the app shell. Stripe
  Checkout and the billing portal rely on this.

---

## Code signing

Unsigned builds trigger SmartScreen ("Windows protected your PC") and users must
click through. For distribution you need an Authenticode certificate — an OV
certificate still warns until reputation accrues; an EV certificate does not.

```ini
CSC_LINK=/path/to/certificate.pfx
CSC_KEY_PASSWORD=...
```

electron-builder picks these up automatically. Never commit them; in CI use the
platform's secret store.

---

## Building in CI

A `windows-latest` runner avoids Wine entirely:

```yaml
jobs:
  windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: npm, cache-dependency-path: frontend/package-lock.json }
      - run: npm ci
        working-directory: frontend
      - run: npm run electron:build:win
        working-directory: frontend
        env:
          CSC_LINK: ${{ secrets.WINDOWS_CERT }}
          CSC_KEY_PASSWORD: ${{ secrets.WINDOWS_CERT_PASSWORD }}
      - uses: actions/upload-artifact@v4
        with:
          name: dayflow-windows
          path: frontend/release/*.exe
```

---

## Icon

`frontend/build/icon.ico` (7 sizes, 16–256px) and `frontend/public/icon.png`
(1024px) are generated from the in-app `CubeLogo` mark on the brand gradient.
`package.json` previously pointed at `public/icon.png`, which did not exist, so
builds silently fell back to the stock Electron icon.

To regenerate after a brand change, see the script in the commit that added them,
or replace both files directly — electron-builder needs the `.ico` at ≥256px.

---

## Troubleshooting

**Blank white window.** The renderer failed to load. Open DevTools from the View
menu and check the console — usually a bad `VITE_DESKTOP_API_BASE_URL` or a CSP
violation.

**Every request fails with a CORS error.** `DJANGO_ALLOW_DESKTOP_ORIGIN` is not
set on the backend.

**"wine is required".** See above — use the `:zip` script, or install Wine.

**The exe has the default Electron icon.** It was built with
`signAndEditExecutable=false`, which is what the `:zip` script passes. Build with
Wine, or on Windows, to get the real icon and metadata.

**Stale content after an update.** Electron caches the renderer per app version.
Bump `version` in `package.json` between builds.
