const path = require('path');
const puppeteer = require('puppeteer');

(async () => {
  const htmlPath = path.resolve(__dirname, 'NASDAQ100_ETF_C.html');
  const fileUrl = 'file://' + htmlPath;
  console.log('[1/4] 启动 Chromium ...');

  const browser = await puppeteer.launch({
    headless: 'new',
    defaultViewport: { width: 1200, height: 1600, deviceScaleFactor: 2 }
  });

  const page = await browser.newPage();
  console.log('[2/4] 打开页面:', fileUrl);
  await page.goto(fileUrl, { waitUntil: 'networkidle0' });

  console.log('[3/4] 等待字体加载 ...');
  await page.evaluateHandle('document.fonts.ready');

  console.log('[4/4] 开始截图 ...');
  for (let i = 1; i <= 5; i++) {
    const selector = '#p' + i;
    const el = await page.$(selector);
    if (!el) { console.warn('  × 未找到', selector); continue; }
    const outPath = path.resolve(__dirname, `NASDAQ100_ETF_C_0${i}.png`);
    await el.screenshot({ path: outPath });
    console.log('  ✓ 已生成', outPath);
  }

  await browser.close();
  console.log('全部完成 ✅');
})().catch(err => {
  console.error('❌ 截图失败:', err);
  process.exit(1);
});
