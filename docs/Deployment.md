# Browser deployment

Live app: https://peiyuwang1018.github.io/knee-linkage-lab/

The site is a static GitHub Pages project. Python runs in a module Web Worker via
[Pyodide](https://pyodide.org/en/stable/usage/webworker.html), pinned to 314.0.8.
There is no Python cloud server. The first visit needs a network connection to
download the runtime from jsDelivr. Browser caching can reduce later downloads;
this is not an offline-installable PWA.

## One solver, two transports

- `kneelab/api.py` dispatches defaults, cycles, scans and CSV exports.
- `server.py` uses that dispatcher for the local HTTP API.
- `static/runtime.js` selects the browser worker only on built Pages HTML.
- `static/solver-worker.mjs` loads the original Python files into Pyodide's virtual
  filesystem, including `chains.json`, and calls the same dispatcher.
- `build_site.py` writes the static assets and Python source bundle to `_site`.
  Relative paths support both a domain root and the `/knee-linkage-lab/` subpath.

Geometry, loading, reactions and manufacturer limits are shared. Browser and
native libm can differ in the last floating-point digits; parity tests use numeric
tolerances. Full multibody dynamics, wear and thermal checks remain outside scope.

Configurations stay in localStorage for each website origin. A saved setting at
localhost will not automatically appear on GitHub Pages. Use Save config / Open
to transfer it. CSV, SVG and configuration downloads happen on the client.

The worker keeps the UI responsive during scans. Cancel terminates the worker and
rejects pending requests; the next calculation starts a fresh worker. Broad scans
can take longer in a browser than in native Python. A reload button is shown if
the Python runtime cannot start.

## Build and publish

```sh
python3 -m unittest discover -s tests -v
node --test tests/test_analysis.cjs
python3 build_site.py
python3 -m http.server 8787 --directory _site --bind 127.0.0.1
```

Repository Settings → Pages → Source must be **GitHub Actions**. Pushing `main`
runs `.github/workflows/pages.yml`: tests, static build, artifact upload, deploy.
Only `_site` is published; local outputs, notes and private configuration are not
part of the site. The repository is public, including its Python solver sources.

Reference: [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

## Browser verification

`tests/browser_cases.json` covers rod geometry, unequal stiffness, hip acceleration,
contact loss, both chain directions, idler layouts, missing ratings and finite scans.
`tests/browser_parity.mjs` compares every returned field with native Python using
absolute tolerance 1e-7 plus relative tolerance 1e-9. It also checks configuration
round trips, CSV/SVG downloads, overload display, navigation, mobile layout, worker
cancellation/restart, and a blocked runtime download.

Run a static server for the built site and `server.py --port 8790` in separate terminals,
then run the script with Node and Playwright installed:

```sh
BASE_URL=http://127.0.0.1:8787/ LOCAL_URL=http://127.0.0.1:8790/ node tests/browser_parity.mjs
```

`BROWSER_EXECUTABLE` can select an installed Chromium-based browser;
`PLAYWRIGHT_MODULE` can select an existing Playwright module. Verification reports
and screenshots go to the ignored `output/browser-deployment/` directory.
