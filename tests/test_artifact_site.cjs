// Copyright 2026 InsightOS
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Run with Playwright available via NODE_PATH; no installation or external writes.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { createHash } = require('node:crypto');

(async () => {
  const base = process.env.SEMANTIC_SITE_URL || 'https://semantic.insightos.cn';
  const browser = await chromium.launch(process.env.SEMANTIC_BROWSER_PATH
    ? { executablePath: process.env.SEMANTIC_BROWSER_PATH }
    : { channel: 'chrome' });
  try {
    const context = await browser.newContext({ permissions: ['clipboard-read', 'clipboard-write'] });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    for (const width of [1440, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      const response = await page.goto(base + '/?lang=zh', { waitUntil: 'networkidle' });
      assert.equal(response.status(), 200);
      assert.match(await page.title(), /Semantic/);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `overflow at ${width}px`);
      await page.locator('#musl-install summary').click();
      assert.match(await page.locator('#musl-command').textContent(), /install\.sh.*[\s\S]*--musl/);
      assert.match(await page.locator('#musl-install').textContent(), /617 MiB/);
      assert.ok(!/--musl/.test(await page.locator('#install-command').textContent()));
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `expanded musl overflow at ${width}px`);
      await page.locator('#copy-command').click();
      assert.equal(await page.evaluate(() => navigator.clipboard.readText()), await page.locator('#install-command').textContent());
      assert.match(await page.locator('.support-note').textContent(), /仅支持 Linux x86_64.*Ubuntu 24.04/);
      assert.match(await page.locator('.support-roadmap').textContent(), /近期.*更多 Linux/);
      assert.match(await page.locator('#install-video source').getAttribute('src'), /semantic-install-d282bc52483d\.mp4$/);
      await page.locator('[data-language="en"]').click();
      assert.equal(await page.locator('html').getAttribute('lang'), 'en');
      assert.equal(await page.locator('[data-language="en"]').getAttribute('aria-pressed'), 'true');
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `English overflow at ${width}px`);
      assert.equal(await page.locator('[data-language-panel="zh"]').isVisible(), false);
      assert.match(await page.locator('.support-note').textContent(), /Linux x86_64 only.*Ubuntu 24.04/);
      assert.match(await page.locator('.support-roadmap').textContent(), /More Linux distributions will be tested soon/);
      assert.match(await page.locator('#install-video source').getAttribute('src'), /semantic-install-en-03290f9242db\.mp4$/);
      assert.ok(await page.locator('#install-video').evaluate(element => element.paused));
      assert.equal(await page.locator('#video-link').getAttribute('href'), await page.locator('#install-video source').getAttribute('src'));
      assert.match(await page.locator('.footer-legal').textContent(), /Copyright © 上海具识智能科技有限公司版权所有/);
      assert.match(await page.locator('.police-filing').textContent(), /沪公网安备31011502404136号/);
      assert.equal(await page.locator('.filing-links a').last().textContent(), '沪ICP备2025112430号');
      assert.equal(await page.locator('.filing-links a').last().getAttribute('href'), 'https://beian.miit.gov.cn/');
      assert.equal(await page.locator('.police-filing img').getAttribute('src'), 'https://assets.insightos.cn/assets/images/guohui.png');
      assert.equal(await page.locator('.police-filing img').getAttribute('alt'), '公安备案');
      assert.ok(await page.locator('.police-filing img').evaluate(element => element.complete && element.naturalWidth > 0));
      assert.ok(await page.locator('.footer-legal').isVisible());
      assert.equal(await page.locator('#script-link').getAttribute('href'), '/install-en.sh');
      assert.match(await page.locator('#musl-command').textContent(), /install-en\.sh.*[\s\S]*--musl/);
      assert.match(await page.locator('#musl-install').textContent(), /Alpine.*musl/);
      assert.equal(await page.locator('.musl-release a').getAttribute('href'), 'https://github.com/insightos-community/quick-start/releases/tag/musl-v0.1.0-1');
      for (const text of await page.locator('[data-i18n]').allTextContents()) {
        assert.ok(!/[\u4e00-\u9fff]/.test(text), `Untranslated English copy: ${text}`);
        assert.ok(!text.includes('undefined'), 'Missing translation');
      }
      for (const text of await page.locator('[data-install-command]').allTextContents()) {
        assert.match(text, /https:\/\/semantic.insightos.cn\/install-en.sh/);
      }
      await page.locator('#copy-command-en').click();
      assert.equal(await page.evaluate(() => navigator.clipboard.readText()), await page.locator('#install-command-en').textContent());
      assert.match(await page.locator('#install-command-en').textContent(), /\/install-en\.sh/);
      const faq = page.locator('.faq details').first();
      await faq.locator('summary').click();
      assert.equal(await faq.getAttribute('open'), '');
      console.log(`PASS layout, clipboard, FAQ: ${width}px`);
    }
    await page.reload({waitUntil: 'networkidle'});
    assert.equal(await page.locator('html').getAttribute('lang'), 'en');
    await page.goto(base, {waitUntil: 'networkidle'});
    assert.equal(await page.locator('html').getAttribute('lang'), 'en');
    await page.locator('[data-language="zh"]').click();
    assert.equal(await page.locator('html').getAttribute('lang'), 'zh-CN');
    assert.match(await page.locator('h1').textContent(), /从语义/);
    assert.equal(await page.locator('#script-link').getAttribute('href'), '/install.sh');
    assert.ok(!(await page.locator('[data-i18n="validated"]').textContent()).match(/Debian|Fedora/));
    const video = page.locator('#install-video');
    assert.equal(await video.getAttribute('preload'), 'none');
    assert.equal(await video.getAttribute('autoplay'), null);
    assert.equal(await video.getAttribute('controls'), '');
    assert.match(await video.locator('source').getAttribute('src'), /^https:\/\/insightos-artifacts\.oss-cn-shanghai\.aliyuncs\.com\/semantic\/media\/.+\.mp4$/);
    await video.evaluate(element => element.play());
    await page.waitForFunction(() => document.getElementById('install-video').currentTime > 0.1);
    assert.ok(await video.evaluate(element => element.videoWidth === 1920 && element.duration > 35));
    await video.evaluate(element => new Promise(resolve => {
      element.addEventListener('seeked', resolve, {once: true});
      element.currentTime = 20;
    }));
    // Re-selecting the same language must not interrupt the current recording.
    await page.locator('[data-language="zh"]').click();
    assert.ok(await video.evaluate(element => element.currentTime >= 20 && !element.paused));
    await page.locator('[data-language="en"]').click();
    assert.ok(await video.evaluate(element => element.currentTime === 0 && element.paused));
    assert.match(await video.locator('source').getAttribute('src'), /semantic-install-en-03290f9242db\.mp4$/);
    await video.evaluate(element => element.play());
    await page.waitForFunction(() => document.getElementById('install-video').currentTime > 0.1);
    assert.ok(await video.evaluate(element => element.videoWidth === 1920 && element.duration > 35 && element.currentSrc.includes('semantic-install-en-')));
    await video.evaluate(element => new Promise(resolve => {
      element.addEventListener('seeked', resolve, {once: true});
      element.currentTime = 20;
    }));
    assert.ok(await video.evaluate(element => element.currentTime >= 20 && !element.paused));
    await video.locator('source').dispatchEvent('error');
    assert.equal(await page.locator('#video-error').isVisible(), true);
    await page.locator('[data-language="zh"]').click();
    assert.ok(await video.evaluate(element => element.currentTime === 0 && element.paused));
    assert.equal(await page.locator('#video-error').isVisible(), false);
    assert.match(await page.locator('#video-link').getAttribute('href'), /semantic-install-d282bc52483d\.mp4$/);
    console.log('PASS language persistence, support roadmap, legal footer, bilingual OSS playback and seeking');
    const storageBlocked = await browser.newContext({locale: 'en-US'});
    await storageBlocked.addInitScript(() => {
      Storage.prototype.getItem = () => { throw new Error('storage blocked'); };
      Storage.prototype.setItem = () => { throw new Error('storage blocked'); };
    });
    const blockedPage = await storageBlocked.newPage();
    await blockedPage.goto(base);
    assert.equal(await blockedPage.locator('html').getAttribute('lang'), 'en');
    await blockedPage.locator('[data-language="zh"]').click();
    assert.equal(await blockedPage.locator('html').getAttribute('lang'), 'zh-CN');
    await storageBlocked.close();
    const noScript = await browser.newContext({javaScriptEnabled: false});
    const noScriptPage = await noScript.newPage();
    await noScriptPage.goto(base, {waitUntil: 'networkidle'});
    assert.equal(await noScriptPage.locator('html').getAttribute('lang'), 'zh-CN');
    assert.match(await noScriptPage.locator('#install-video source').getAttribute('src'), /semantic-install-d282bc52483d\.mp4$/);
    assert.ok(await noScriptPage.locator('.footer-legal').isVisible());
    assert.ok(await noScriptPage.locator('.police-filing img').evaluate(element => element.complete && element.naturalWidth > 0));
    await noScript.close();
    for (const [path, mime] of [['/', 'text/html'], ['/style.css', 'text/css'], ['/site.js', 'application/javascript'], ['/favicon.svg', 'image/svg+xml'], ['/install.sh', 'text/plain'], ['/install-en.sh', 'text/plain']]) {
      const response = await context.request.get(base + path);
      assert.equal(response.status(), 200, path);
      assert.ok(response.headers()['content-type'].startsWith(mime), path);
      assert.equal(response.headers()['x-content-type-options'], 'nosniff');
      assert.match(response.headers()['content-security-policy'], /media-src https:\/\/insightos-artifacts\.oss-cn-shanghai\.aliyuncs\.com/);
      assert.match(response.headers()['content-security-policy'], /img-src 'self' https:\/\/assets\.insightos\.cn;/);
      if (path === '/install.sh' || path === '/install-en.sh') {
        const hash = bytes => createHash('sha256').update(bytes).digest('hex');
        assert.equal(hash(await response.body()), hash(readFileSync(resolve(__dirname, '../artifacts' + path))));
      }
      console.log(`PASS content, headers: ${path}`);
    }
    for (const path of ['/not-a-real-page', '/compose.yaml', '/nginx-static.conf', '/README.md', '/oss.env', '/.env']) {
      const response = await context.request.get(base + path);
      assert.ok([403, 404].includes(response.status()), path);
    }
    assert.deepEqual(errors, []);
    console.log('PASS no exposed configuration, no browser errors, installer matches local SHA-256');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
