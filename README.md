# 小红书图文卡片项目

用 HTML + CSS 写 1080×1440 的小红书卡片，再用 Puppeteer 批量截成 2160×2880 的高清 PNG 直接发布。

## 目录结构

```
xiaohongshu/
├── shot.js                 # 通用截图脚本（全项目唯一一份）
├── package.json
├── README.md
├── .kiro/skills/           # Kiro 读取位置（开源 skill 软链接到 ../skills）
└── posts/                  # 所有选题，按题材分四类
    ├── fund_notes/         # 单只基金 · 5 页深度笔记
    ├── fund_compare/       # 基金横向对比
    ├── market_index/       # 指数 / 市场题材
    └── knowledge/          # 规则科普与研究
```

### posts/fund_notes/ · 单只基金 5 页笔记

一只基金一个目录，产出 `fetch.py` + `data.json` + 5 页 HTML + 5 张 PNG + 文案。

| 目录 | 基金 |
|---|---|
| `efund_qdii/` | 易方达全球成长精选(QDII)C 012922 |
| `fuguo_tech_internet/` | 富国全球科技互联网 100055 |
| `greatwall_ev/` | 长城全球新能源车(QDII)C 018036 |
| `guofu_qdii/` | 国富全球科技互联(QDII)C 021842 |
| `huaxia_global_tech_pioneer/` | 华夏全球科技先锋(QDII)C 024239 |
| `jianxin_emerging_qdii/` | 建信新兴市场混合(QDII)A 539002 |
| `jiashi_qdii/` | 嘉实全球产业升级(QDII)C 017731 |
| `puyin_global_smart_tech/` | 浦银安盛全球智能科技(QDII)C 014002 |
| `tianhong_global_manufacturing/` | 天弘全球高端制造(QDII)C 016665 |
| `yinhu_016702/` | 银华海外数字经济 016702 |

### posts/fund_compare/ · 横向对比

| 目录 | 选题 |
|---|---|
| `nasdaq100_active_funds/` | 纳指 100 主动型基金全景（收益 / 回撤 / 限额 / 持仓） |
| `nasdaq100_passive_funds/` | 纳指 100 C 类基金对比（费率 / 跟踪误差 / 限购） |

### posts/market_index/ · 指数与市场

| 目录 | 选题 |
|---|---|
| `nasdaq_overview/` | 纳斯达克指数总览（5 页） |
| `nasdaq_annual_returns/` | 纳斯达克 / 纳指 100 历年回报率方块图 |
| `nasdaq_extreme_days/` | 纳指历史十大单日涨幅 / 跌幅 |
| `sse_extreme_days/` | 上证指数历史十大单日涨幅 / 跌幅 |

### posts/knowledge/ · 科普与研究

| 目录 | 选题 |
|---|---|
| `qdii_trading_rules/` | 海外 QDII 基金交易规则 |
| `qdii_valuation_model/` | QDII 主动基金净值估算模型与回测（12 页 + Python 模型 + 报告） |

## 截图脚本 · `shot.js`

全项目共用根目录这一份，按位置参数决定截哪些 HTML。**在项目根目录执行。**

```bash
# 截单个文件
node shot.js posts/market_index/nasdaq_extreme_days/NASDAQ_WORST_DAYS.html

# 截整个目录下所有 .html
node shot.js posts/market_index/nasdaq_extreme_days

# 多个目标混合（目录 + 文件）
node shot.js posts/market_index/nasdaq_annual_returns posts/fund_notes/yinhu_016702/YINHU.html
```

也可以走 npm script：

```bash
npm run shot -- posts/fund_notes/yinhu_016702
```

### 行为

- HTML 中每个 `<div class="card">` 节点单独截一张
- 单卡输出 `<basename>.png`；多卡输出 `<basename>_01.png` / `_02.png` ...
- 输出与原 HTML 同目录
- `deviceScaleFactor: 2`，最终 2160×2880，符合小红书 3:4 高清规格
- 等字体加载最长 10 秒，超时自动继续渲染，不卡流水线

> ⚠️ 不要在选题目录里再放 shot.js 副本。历史上每个目录一份，已全部收敛到根目录这一份。

### HTML 模板要求

新卡片必须满足两点才能被脚本正确识别：

1. 每页用 `<div class="card" id="p1">` 包裹（多页 `id="p2" / "p3"` 依次类推）
2. 卡片自身固定 `width: 1080px; height: 1440px;`

参考样板：`posts/market_index/nasdaq_annual_returns/NASDAQ_BLOCKS.html`、`.kiro/skills/xhs-fund-holdings-analysis/example.html`

## 字体

视觉风格依赖三套衬线字体：

| 用途 | 字体 |
|---|---|
| 中文标题 | Noto Serif SC |
| 英文 / 数字 | DM Serif Display |
| 装饰水印 | Cormorant Garamond |

**推荐装到本地**，避免截图时 Google Fonts CDN 超时降级到系统兜底字体。

```bash
brew install --cask font-noto-serif-sc font-dm-serif-display font-cormorant-garamond
```

## 安装与初始化

```bash
npm install
brew install --cask font-noto-serif-sc font-dm-serif-display font-cormorant-garamond   # 仅首次
node shot.js posts/market_index/sse_extreme_days                                        # 试截一次
```

## 视觉风格规范

完整规范见 `.kiro/skills/xhs-dark-luxe-gold-ui/SKILL.md`，要点：

- **画布**：1080×1440px（小红书 3:4 竖图）
- **配色**：深色奠华金主题
  - 背景：靛蓝渐变 `#05060b → #0b1020`
  - 主金色：`#d4b26a`
  - 红涨：`#ef3b3b`，绿跌：`#17b26a`（沿用中国市场习惯）
- **字号**：标题 46~52px，正文 16~22px，关键数字 34~54px
- **必备装饰**：四角金色 L 型角标、金色分割线、双层防伪水印（背景斜排重复 + 中央印章）

## 创作 skill

### 开源版 · 独立仓库 `../skills/`

把 `fund_notes` 和 `market_index` 两条流水线的风格浓缩成一个符合 Agent Skills 规范的可移植 skill，MIT 许可，放在与本项目**同级的独立目录**里，方便单独开源。

```
personal/
├── xiaohongshu/                        ← 本项目（选题与产物）
└── skills/                             ← 开源 skill 仓库
    ├── package.json                    自带 puppeteer 依赖
    ├── LICENSE                         MIT
    └── xhs-dark-luxe-gold-cards/
        ├── SKILL.md                    入口：铁律 + 五步工作流
        ├── references/                 design-tokens / layout-recipes / copywriting / acceptance
        ├── assets/                     card-skeleton.html（空白骨架）+ components.css（组件库）
        ├── scripts/                    shot.js（截图）+ check_cards.js（自动验收）
        └── examples/                   2 页榜单示例 + 5 页笔记示例（数据全虚构）
```

亮点是 `scripts/check_cards.js`：在真实浏览器里量每一行文字的墨迹，自动查压字、越界、底部安全区、文本裁切、页码错位、字体降级，把「截完人眼逐张核对」变成一条命令。

在本项目里可以直接拿它体检卡片：

```bash
npm run check:posts                                    # 体检 posts/ 下所有卡片
npm run check -- posts/market_index/nasdaq_overview    # 查单个目录
```

在 skill 仓库里跑它自己的回归测试：

```bash
cd ../skills && npm run verify        # 跑示例 + 严格验收，应为 0 error 0 warn
```

`.kiro/skills/xhs-dark-luxe-gold-cards` 是指向 `../skills/xhs-dark-luxe-gold-cards` 的软链接，Kiro 里直接可用。软链接本身已 gitignore，克隆本仓库后需要重建：

```bash
ln -sfn ../../../skills/xhs-dark-luxe-gold-cards .kiro/skills/xhs-dark-luxe-gold-cards
```

### 私有版 · `.kiro/skills/`

早期的两个 skill，仍在用：

- **`xhs-dark-luxe-gold-ui`** — 深色奠华金视觉规范 + 小红书文案规则
- **`xhs-fund-holdings-analysis`** — 单只基金 5 页笔记流程，自带 `scripts/fetch.py`（东财数据抓取）

> 这两个的内容已被开源版覆盖，且 `example.html` 里是真实作品和个人水印。确认开源版够用之后可以删掉，避免三个 skill 触发条件重叠。

## 新增一个选题

1. 在 `posts/` 下对应分类里建目录，如 `posts/market_index/my_topic/`
2. 写 `MY_TOPIC.html`（1080×1440 + `<div class="card" id="p1">` 结构）
3. 根目录执行 `node shot.js posts/market_index/my_topic`
4. 补一份 `小红书文案.md`（标题 30 个候选 + 正文 + 话题标签）

## License

ISC
