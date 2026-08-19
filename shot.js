// shot.js —— 项目根目录通用截图脚本
//
// 把任意 1080×1440 卡片 HTML（每页一个 <div class="card" id="p1|p2|...">）
// 批量截成小红书可发布的高清 PNG（2160×2880, deviceScaleFactor=2）。
//
// 用法（在项目根目录执行）：
//
//   node shot.js                                    # 扫描当前目录下所有 .html
//   node shot.js nasdaq_worst_days                  # 截整个文件夹下所有 .html
//   node shot.js nasdaq_worst_days/X.html           # 截单个文件
//   node shot.js dir1 dir2/file.html                # 多个目标混合（目录 + 文件）
//
// 也可通过 npm:
//
//   npm run shot -- nasdaq_worst_days
//   npm run shot -- nasdaq_blocks/NASDAQ_BLOCKS.html
//
// 输出：
//   与原 HTML 同目录，命名为 <basename>.png（单卡）或 <basename>_01.png ...（多卡）

const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer');

const ROOT = __dirname;

/** 把 CLI 参数解析成一组绝对路径的 .html 文件 */
function resolveHtmlFiles(args) {
  if (args.length === 0) {
    // 默认：扫描脚本所在目录（项目根）下所有 .html
    return fs
      .readdirSync(ROOT)
      .filter(f => f.toLowerCase().endsWith('.html'))
      .map(f => path.resolve(ROOT, f));
  }

  const out = [];
  for (const raw of args) {
    const abs = path.isAbsolute(raw) ? raw : path.resolve(ROOT, raw);
    if (!fs.existsSync(abs)) {
      console.warn('  × 路径不存在，跳过:', raw);
      continue;
    }

    const stat = fs.statSync(abs);
    if (stat.isFile()) {
      if (abs.toLowerCase().endsWith('.html')) {
        out.push(abs);
      } else {
        console.warn('  × 非 .html 文件，跳过:', raw);
      }
    } else if (stat.isDirectory()) {
      const htmls = fs
        .readdirSync(abs)
        .filter(f => f.toLowerCase().endsWith('.html'))
        .map(f => path.resolve(abs, f));
      if (htmls.length === 0) {
        console.warn('  × 目录下没有 .html 文件，跳过:', raw);
      }
      out.push(...htmls);
    }
  }
  return out;
}

(async () => {
  const args = process.argv.slice(2);
  const files = resolveHtmlFiles(args);

  if (files.length === 0) {
    console.error('❌ 未找到任何 .html 文件');
    console.error('用法: node shot.js [<dir|file> ...]');
    process.exit(1);
  }

  console.log(`[1/2] 启动 Chromium，共 ${files.length} 个 HTML 待处理 ...`);
  const browser = await puppeteer.launch({
    headless: 'new',
    defaultViewport: { width: 1080, height: 1440, deviceScaleFactor: 2 },
  });

  for (const file of files) {
    const dir = path.dirname(file);
    const base = path.basename(file, path.extname(file));
    const fileUrl = 'file://' + file;

    const page = await browser.newPage();
    console.log(`\n[${base}] 打开: ${path.relative(ROOT, file)}`);

    try {
      await page.goto(fileUrl, {
        waitUntil: 'domcontentloaded',
        timeout: 60_000,
      });
    } catch (e) {
      console.warn('  × 页面加载失败:', e.message);
      await page.close();
      continue;
    }

    // 等 webfont（最长 10 秒，超时则继续渲染）
    try {
      await Promise.race([
        page.evaluateHandle('document.fonts.ready'),
        new Promise((_, rej) =>
          setTimeout(() => rej(new Error('fonts timeout')), 10_000)
        ),
      ]);
    } catch (e) {
      console.log('  ⚠ 字体加载超时，继续渲染：', e.message);
    }
    await new Promise(r => setTimeout(r, 800));

    // 找到所有 .card 节点（单卡 / 多卡通吃）
    const cardCount = await page.$$eval('.card', els => els.length);
    if (cardCount === 0) {
      console.warn('  × 未找到 .card 元素，跳过');
      await page.close();
      continue;
    }

    for (let i = 0; i < cardCount; i++) {
      const sel = `.card:nth-of-type(${i + 1})`;
      const el = await page.$(sel);
      if (!el) {
        console.warn('  × 未找到', sel);
        continue;
      }
      const suffix =
        cardCount === 1 ? '' : `_${String(i + 1).padStart(2, '0')}`;
      const out = path.resolve(dir, `${base}${suffix}.png`);
      await el.screenshot({ path: out });
      console.log('  ✓', path.relative(ROOT, out));
    }

    await page.close();
  }

  await browser.close();
  console.log('\n[2/2] 全部完成 ✅');
})().catch(err => {
  console.error('❌ 截图失败:', err);
  process.exit(1);
});
