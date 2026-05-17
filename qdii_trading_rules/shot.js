// shot.js —— 批量截图：QDII 基金交易规则全解
const path = require('path');
const puppeteer = require('puppeteer');

const tasks = [
  { file: 'QDII_RULES.html', prefix: 'QDII_RULES', pages: 6 },
];

(async () => {
  console.log('[1/2] 启动 Chromium ...');
  const browser = await puppeteer.launch({
    headless: 'new',
    defaultViewport: { width: 1200, height: 1600, deviceScaleFactor: 2 }
  });

  for (const t of tasks) {
    const fileUrl = 'file://' + path.resolve(__dirname, t.file);
    const page = await browser.newPage();
    console.log(`\n[${t.prefix}] 打开:`, t.file);
    await page.goto(fileUrl, { waitUntil: 'networkidle0' });
    await page.evaluateHandle('document.fonts.ready');
    await new Promise(r => setTimeout(r, 800));

    for (let i = 1; i <= t.pages; i++) {
      const sel = '#p' + i;
      const el = await page.$(sel);
      if (!el) { console.warn('  × 未找到', sel); continue; }
      const num = String(i).padStart(2, '0');
      const out = path.resolve(__dirname, `${t.prefix}_${num}.png`);
      await el.screenshot({ path: out });
      console.log('  ✓', `${t.prefix}_${num}.png`);
    }
    await page.close();
  }

  await browser.close();
  console.log('\n[2/2] 全部完成 ✅');
})().catch(err => {
  console.error('❌ 截图失败:', err);
  process.exit(1);
});
