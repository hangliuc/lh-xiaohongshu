// shot.js —— 批量截图：V1 深色奠华金 (EFUND)
const path = require('path');
const puppeteer = require('puppeteer');

const tasks = [
  { file: 'EFUND.html', prefix: 'EFUND', pages: 5 },
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
    await new Promise(r => setTimeout(r, 600));

    for (let i = 1; i <= t.pages; i++) {
      const sel = '#p' + i;
      const el = await page.$(sel);
      if (!el) { console.warn('  × 未找到', sel); continue; }
      const out = path.resolve(__dirname, `${t.prefix}_0${i}.png`);
      await el.screenshot({ path: out });
      console.log('  ✓', `${t.prefix}_0${i}.png`);
    }
    await page.close();
  }

  await browser.close();
  console.log('\n[2/2] 全部完成 ✅');
})().catch(err => {
  console.error('❌ 截图失败:', err);
  process.exit(1);
});
