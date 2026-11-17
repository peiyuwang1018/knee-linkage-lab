'use strict';
// The build marks static pages explicitly; local mode keeps using server.py.
window.KneeRuntime = (() => {
  const browser = document.documentElement.dataset.solver === 'browser';
  const base = new URL('./', document.currentScript.src);
  let worker, serial = 0, failed = false, initialized = false, busyTimer;
  const pending = new Map();
  let bar, label, action;
  const bootControls = browser ? [...document.querySelectorAll('body > header, body > main')] : [];
  if (browser) {
    for (const control of bootControls) control.inert = true;
    bar = document.createElement('div');
    bar.className = 'runtime-status';
    bar.hidden = true;
    label = document.createElement('span');
    label.setAttribute('role', 'status');
    action = document.createElement('button');
    action.type = 'button';
    action.textContent = 'Cancel';
    bar.append(label, action);
    document.body.append(bar);
    action.onclick = () => {
      if (failed || !initialized) { location.reload(); return; }
      reset('Calculation cancelled. Run it again when ready.');
      bar.hidden = true;
    };
  }
  function show(text) { label.textContent = text; bar.hidden = false; }
  function reset(reason) {
    worker?.terminate();
    worker = undefined;
    clearTimeout(busyTimer);
    for (const job of pending.values()) job.reject(Error(reason));
    pending.clear();
  }
  function failure(reason) {
    reset(reason);
    failed = true;
    action.textContent = 'Reload';
    show(reason);
  }
  function startWorker() {
    failed = false;
    initialized = false;
    action.textContent = 'Reload';
    worker = new Worker(new URL('./solver-worker.mjs', base), {type: 'module'});
    worker.onmessage = ({data}) => {
      if (data.status) { show(data.status); return; }
      if (data.fatal) { failure('Python could not start. Check your connection and reload.'); return; }
      const job = pending.get(data.id);
      if (!job) return;
      pending.delete(data.id);
      initialized = true;
      action.textContent = 'Cancel';
      if (job.initial && !data.error) for (const control of bootControls) control.inert = false;
      if (data.error) job.reject(Error(data.error)); else job.resolve(data.result);
      if (!pending.size) { clearTimeout(busyTimer); bar.hidden = true; }
      if (data.error && job.initial) failure('Python could not start. Check your connection and reload.');
    };
    worker.onerror = event => {
      event.preventDefault();
      failure('Python could not start. Check your connection and reload.');
    };
    worker.onmessageerror = () => failure('Could not read solver results. Reload to retry.');
    show('Loading Python… First visit may take a moment.');
  }
  async function request(path, body) {
    if (!browser) {
      const response = await fetch(new URL(path.replace(/^\//, ''), base), body === undefined ? {} : {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
      });
      if (!response.ok) {
        const error = await response.json();
        throw Error(error.error || 'Request failed');
      }
      return path.endsWith('.csv') ? response.text() : response.json();
    }
    if (!worker) startWorker();
    const id = ++serial;
    if (!pending.size && initialized) busyTimer = setTimeout(() => show('Calculating… You can cancel a long scan.'), 1200);
    return new Promise((resolve, reject) => {
      pending.set(id, {resolve, reject, initial: path.endsWith('/defaults')});
      worker.postMessage({id, path, body});
    });
  }
  return {request, mode: browser ? 'browser' : 'local'};
})();
