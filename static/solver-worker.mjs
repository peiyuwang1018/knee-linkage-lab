// This worker executes the repository's Python sources without translating mechanics.
const PYODIDE_URL = 'https://cdn.jsdelivr.net/pyodide/v314.0.8/full/pyodide.mjs';

async function initialize() {
  self.postMessage({status: 'Loading Python… First visit may take a moment.'});
  const [{loadPyodide}, response] = await Promise.all([
    import(PYODIDE_URL), fetch(new URL('./kneelab-sources.json', import.meta.url))
  ]);
  if (!response.ok) throw Error('Could not load solver files. Reload this page to retry.');
  const sources = await response.json();
  const python = await loadPyodide();
  python.FS.mkdirTree('/app/kneelab');
  for (const [name, content] of Object.entries(sources)) {
    if (!/^[a-z_]+\.(py|json)$/.test(name)) throw Error('Invalid solver bundle.');
    python.FS.writeFile('/app/kneelab/' + name, content, {encoding: 'utf8'});
  }
  python.runPython("import sys\nsys.path.insert(0, '/app')\nfrom kneelab.api import dispatch_json");
  return python.globals.get('dispatch_json');
}

let ready;
// Each request is synchronous once Python is ready. Promise order preserves dispatch order.
self.onmessage = async ({data: {id, path, body}}) => {
  let dispatch;
  try {
    ready ||= initialize();
    dispatch = await ready;
  } catch (error) {
    self.postMessage({id, error: error.message || String(error), fatal: true});
    return;
  }
  try {
    const result = JSON.parse(dispatch(path, JSON.stringify(body ?? null)));
    self.postMessage({id, result});
  } catch (error) {
    self.postMessage({id, error: error.message || String(error)});
  }
};
