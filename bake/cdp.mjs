// 无依赖的 Chrome DevTools Protocol 小工具（Node ≥ 22：内置 WebSocket / fetch）。
// 用于导出场景、截图、帧率基准、运行时集成测试。全部跑在无头 Chrome + ANGLE Metal 上。
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

export const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const sleep = ms => new Promise(r => setTimeout(r, ms));

// 路径含中文（"修复"），必须走 pathToFileURL 编码
export function fileUrl(path, hash = '') {
  return pathToFileURL(path).href + (hash ? '#' + hash : '');
}

export async function launch({ width = 1600, height = 900 } = {}) {
  const port = 9300 + Math.floor(Math.random() * 600);
  const userDir = mkdtempSync(join(tmpdir(), 'cdp-'));
  const proc = spawn(CHROME, [
    '--headless=new', '--use-angle=metal', '--enable-webgl', '--ignore-gpu-blocklist',
    '--hide-scrollbars', `--window-size=${width},${height}`,
    `--remote-debugging-port=${port}`, `--user-data-dir=${userDir}`,
    '--no-first-run', '--no-default-browser-check', 'about:blank',
  ], { stdio: 'ignore' });
  let page = null;
  for (let i = 0; i < 150 && !page; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      page = list.find(t => t.type === 'page') || null;
    } catch { /* 还没起来 */ }
    if (!page) await sleep(200);
  }
  if (!page) { proc.kill('SIGKILL'); throw new Error('Chrome 没有启动'); }
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let seq = 0;
  const pending = new Map();
  const logs = [];
  ws.onmessage = ev => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
    } else if (msg.method === 'Runtime.consoleAPICalled') {
      logs.push(`${msg.params.type}: ` + msg.params.args.map(a => a.value ?? a.description ?? '').join(' '));
    } else if (msg.method === 'Runtime.exceptionThrown') {
      const d = msg.params.exceptionDetails;
      logs.push('exception: ' + (d.exception?.description || d.text));
    }
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++seq;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
  await send('Page.enable');
  await send('Runtime.enable');

  // Node 侧也计时：导航途中发出的 evaluate，其执行上下文被销毁后 Chrome 可能永远不回包 → 不能无限等
  async function evaluate(expression, timeout = 600000) {
    let timer;
    const r = await Promise.race([
      send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true, timeout }),
      new Promise((_, rej) => { timer = setTimeout(() => rej(new Error('CDP 无响应: ' + expression.slice(0, 60))), timeout + 2000); }),
    ]).finally(() => clearTimeout(timer));     // 不清掉的话，计时器会让 Node 进程空等到超时才退出
    if (r.exceptionDetails) {
      throw new Error('页面内报错: ' + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
    }
    return r.result.value;
  }
  async function waitFor(expr, ms = 120000) {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) {
      try { if (await evaluate(`!!(${expr})`, 5000)) return; } catch { /* 页面还在加载 / 上下文刚被导航销毁 */ }
      await sleep(250);
    }
    throw new Error('等待超时: ' + expr);
  }
  async function goto(url, readyExpr = "document.readyState === 'complete' && typeof composer !== 'undefined'") {
    await send('Page.navigate', { url });
    await waitFor(readyExpr);
  }
  // 只取 WebGL 画布（preserveDrawingBuffer=true），不含 DOM 界面与 2D 叠层（辉光/颗粒/暗角）
  async function canvasPNG(path) {
    const b64 = await evaluate(`renderer.domElement.toDataURL('image/png').split(',')[1]`);
    writeFileSync(path, Buffer.from(b64, 'base64'));
  }
  async function close() {
    try { ws.close(); } catch { /* 已关闭 */ }
    proc.kill('SIGKILL');
    await sleep(300);
    rmSync(userDir, { recursive: true, force: true });
  }
  return { send, evaluate, waitFor, goto, canvasPNG, close, logs };
}
