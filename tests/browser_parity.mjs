// Run after build_site.py, with a static server and the local server available.
// npm install --no-save playwright; npx playwright install chromium
// BASE_URL=http://127.0.0.1:8789/_site/ LOCAL_URL=http://127.0.0.1:8790/ node tests/browser_parity.mjs
import assert from 'node:assert/strict';
import {readFile, mkdir, writeFile} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.BASE_URL || 'http://127.0.0.1:8789/_site/';
const local = process.env.LOCAL_URL || 'http://127.0.0.1:8790/';
const cases = JSON.parse(await readFile(new URL('./browser_cases.json', import.meta.url)));
const expected = JSON.parse(execFileSync('python3', ['-c', `
import json
from kneelab.api import dispatch
cases=json.load(open('tests/browser_cases.json'))
print(json.dumps([dispatch(c['path'],c.get('body')) for c in cases],allow_nan=False))
`], {cwd: root, maxBuffer: 30 * 1024 * 1024}));
function compare(actual, expected, path = '') {
  if (typeof expected === 'number') {
    assert.equal(typeof actual, 'number', path);
    assert.ok(Math.abs(actual - expected) <= 1e-7 + 1e-9 * Math.abs(expected), `${path}: ${actual} != ${expected}`);
  } else if (Array.isArray(expected)) {
    assert.equal(actual.length, expected.length, path);
    expected.forEach((v, i) => compare(actual[i], v, `${path}[${i}]`));
  } else if (expected && typeof expected === 'object') {
    assert.deepEqual(Object.keys(actual).sort(), Object.keys(expected).sort(), path);
    for (const key of Object.keys(expected)) compare(actual[key], expected[key], `${path}.${key}`);
  } else assert.equal(actual, expected, path);
}
const browser = await chromium.launch({headless: true, ...(process.env.BROWSER_EXECUTABLE ? {executablePath: process.env.BROWSER_EXECUTABLE} : {})});
const report = [];
const output = join(root, 'output', 'browser-deployment');
await mkdir(output, {recursive: true});
try {
  const context = await browser.newContext({viewport: {width: 1600, height: 1000}, acceptDownloads: true});
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  const started = Date.now();
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector('#status')?.textContent.includes('frames'), null, {timeout: 180000});
  assert.equal(await page.evaluate(() => KneeRuntime.mode), 'browser');
  report.push({name: 'first-load', seconds: (Date.now() - started) / 1000});
  for (let i = 0; i < cases.length; i++) {
    const test = cases[i], time = Date.now();
    const actual = await page.evaluate(c => KneeRuntime.request(c.path, c.body), test);
    compare(actual, expected[i], test.name);
    const response = await fetch(new URL(test.path.slice(1), local), test.body ? {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(test.body)
    } : {});
    assert.ok(response.ok);
    compare(await response.json(), expected[i], 'local/' + test.name);
    report.push({name: test.name, seconds: (Date.now() - time) / 1000, pass: true});
    console.log('PASS', test.name);
  }
  const invalid = await page.evaluate(async () => {
    try { await KneeRuntime.request('/api/cycle', {config: {n: 8}}); return ''; }
    catch (e) { return e.message; }
  });
  assert.match(invalid, /n must be/);
  for (const path of ['/api/cycle.csv', '/api/chain/cycle.csv', '/api/scan.csv']) {
    const text = await page.evaluate(p => KneeRuntime.request(p, {config: {}, grid: {n: [2]}}), path);
    assert.ok(typeof text === 'string' && text.includes('\n') && !text.includes('NaN'));
  }
  await page.screenshot({path: join(output, 'linkage-desktop.png')});
  const csv = page.waitForEvent('download');
  await page.locator('#exportCsv').click();
  assert.equal((await csv).suggestedFilename(), 'knee-cycle.csv');
  const svg = page.waitForEvent('download');
  await page.locator('#exportSvg').click();
  assert.equal((await svg).suggestedFilename(), 'knee-frame.svg');
  await page.locator('a.chain-nav').click();
  await page.waitForFunction(() => document.querySelector('#status')?.textContent.includes('samples'), null, {timeout: 180000});
  assert.ok(page.url().startsWith(base));
  assert.match(await page.locator('#chainLoadUtilization').textContent(), /98\.7/);
  await page.locator('#task_mass_kg').fill('90');
  await page.waitForFunction(() => document.querySelector('#chainLoadState')?.textContent.includes('Over'));
  await page.screenshot({path: join(output, 'chain-desktop.png')});
  const save = page.waitForEvent('download');
  await page.locator('#save').click();
  const file = await save;
  const configPath = join(output, file.suggestedFilename());
  await file.saveAs(configPath);
  const saved = JSON.parse(await readFile(configPath));
  assert.equal(saved.config.mass_kg, 90);
  await page.locator('#reset').click();
  await page.waitForFunction(() => document.querySelector('#task_mass_kg').value === '70');
  await page.locator('#file').setInputFiles(configPath);
  await page.waitForFunction(() => document.querySelector('#task_mass_kg').value === '90');
  await page.waitForFunction(() => document.querySelector('#chainLoadState')?.textContent.includes('Over'));
  const chainCsv = page.waitForEvent('download');
  await page.locator('#csv').click();
  assert.equal((await chainCsv).suggestedFilename(), 'chain-cycle.csv');
  await page.evaluate(() => {
    window.heartbeat = 0;
    window.beatTimer = setInterval(() => window.heartbeat++, 50);
    window.scanPending = KneeRuntime.request('/api/chain/scan', {config: {input_teeth_min: 11, input_teeth_max: 80}}).catch(e => e.message);
  });
  await page.locator('.runtime-status button').filter({hasText: 'Cancel'}).waitFor({state: 'visible', timeout: 30000});
  assert.ok(await page.evaluate(() => window.heartbeat > 5), 'UI stays responsive during scan');
  await page.locator('.runtime-status button').click();
  assert.match(await page.evaluate(() => window.scanPending), /cancelled/);
  await page.evaluate(() => clearInterval(window.beatTimer));
  const resumed = await page.evaluate(() => KneeRuntime.request('/api/chain/cycle', {config: {}}));
  compare(resumed, expected[cases.findIndex(c => c.name === 'chain-dual-idlers')], 'restart-after-cancel');
  await page.setViewportSize({width: 390, height: 844});
  await page.screenshot({path: join(output, 'chain-mobile.png')});
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  assert.deepEqual(errors, []);
  const blocked = await browser.newContext();
  await blocked.route('https://cdn.jsdelivr.net/**', route => route.abort());
  const failPage = await blocked.newPage();
  await failPage.goto(base);
  await failPage.locator('.runtime-status span').filter({hasText: 'Python could not start. Check your connection and reload.'}).waitFor({timeout: 30000});
  assert.ok(await failPage.locator('.runtime-status button').filter({hasText: 'Reload'}).isVisible());
  await blocked.close();
  report.push({name: 'exports-import-navigation-overload-cancel-restart-mobile-network-error', pass: true});
  await writeFile(join(output, 'report.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
} finally { await browser.close(); }
