---
name: "xhs-dark-luxe-gold-ui"
description: "制作小红书「深色奠华金 (Dark Luxe Gold)」风格的 1080×1440 HTML 可视化卡片，并配套生成发布用的标题 / 正文 / 话题标签。覆盖配色、字体、装饰、布局、截图全套视觉规范，以及通用小红书文案规则。当需要做深色金融风、深色奢华风的小红书图文卡片时使用。"
---

# 小红书 · 深色奠华金 UI 卡片 Skill

## 输出结构

```
{topic_folder}/
├── {PREFIX}.html         # 单页或多页合一
├── {PREFIX}_01.png       # 截图产物
└── 小红书文案.md         # 标题 / 正文 / 标签
```

每页一个 `<div class="card" id="p1"> ... id="pN">`，多页纵向排列，截图按 `.card` 节点逐页输出。

⚠ **不要在 topic 目录里放 shot.js**。项目根目录有唯一一份通用截图脚本，直接传路径调用即可。

## 画布规格

- 固定 **1080×1440px**（小红书 3:4 竖图），不要改尺寸
- 截图 deviceScaleFactor: 2

## Color tokens

```css
:root{
  --bg-0:#05060b; --bg-1:#0b1020; --bg-2:#141a2e;
  --line:rgba(255,255,255,.08);
  --text:#e7ecf3; --muted:#8a93a6;
  --gold:#d4b26a; --gold-soft:#f2e9d2;
  --up:#ef3b3b; --up-deep:#a81818;     /* 中国市场红涨 */
  --down:#17b26a; --down-deep:#0b7a46; /* 中国市场绿跌 */
  --blue:#5b8bff;
}
```

## 卡片背景

```css
.card{
  width:1080px; height:1440px; position:relative;
  background:
    radial-gradient(1400px 800px at 120% -10%,rgba(212,178,106,.16),transparent 60%),
    radial-gradient(1200px 700px at -20% 30%,rgba(239,59,59,.12),transparent 60%),
    radial-gradient(1200px 700px at 120% 110%,rgba(23,178,106,.10),transparent 60%),
    linear-gradient(180deg,#05060b 0%,#0b1020 50%,#070a14 100%);
  overflow:hidden; border-radius:8px;
  box-shadow:0 30px 80px rgba(0,0,0,.6);
}
```

## 字体

```html
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;500;600;700;900&family=DM+Serif+Display&family=Cormorant+Garamond:ital,wght@0,500;0,600;0,700;1,500;1,600;1,700&display=swap" rel="stylesheet">
```

| 用途 | 字体 | 权重 |
|------|------|------|
| 中文标题 | `Noto Serif SC` | 900 |
| 英文/数字 | `DM Serif Display` | — |
| 英文水印 | `Cormorant Garamond` | 600 italic |
| 数据表格 | `Inter` | 300-700 |

标题渐变：
```css
background:linear-gradient(180deg,#fff 0%,#f3e3b8 55%,#d4b26a 100%);
-webkit-background-clip:text; background-clip:text; color:transparent;
```

## 必备装饰

四角金色 L 型角标（每页都要）：
```css
.corner{position:absolute;width:72px;height:72px;border:1.5px solid rgba(212,178,106,.55)}
.corner.tl{top:54px;left:54px;border-right:none;border-bottom:none}
.corner.tr{top:54px;right:54px;border-left:none;border-bottom:none}
.corner.bl{bottom:54px;left:54px;border-right:none;border-top:none}
.corner.br{bottom:54px;right:54px;border-left:none;border-top:none}
```

分割线：`linear-gradient(90deg,transparent,var(--gold),transparent)`

## 防伪水印（必备，双层叠加）

### 第一层：全页斜排重复文字（背景层，z-index:1）

铺满整张卡片的低透明度重复文字，类似人民币防伪线效果，防裁切盗用。

```css
.watermark{
  position:absolute;top:0;left:0;right:0;bottom:0;
  z-index:1;pointer-events:none;overflow:hidden;
}
.watermark-inner{
  position:absolute;top:-10%;left:-10%;width:120%;height:120%;
  transform:rotate(-28deg);
  display:flex;flex-direction:column;gap:80px;
  padding-top:60px;
}
.watermark-line{
  font-family:"Cormorant Garamond",serif;font-style:italic;font-weight:600;
  font-size:16px;letter-spacing:8px;
  color:rgba(212,178,106,.045);
  white-space:nowrap;line-height:1;
}
```

```html
<div class="watermark">
  <div class="watermark-inner">
    <div class="watermark-line">KEYWORD · 品牌名 · KEYWORD · 品牌名 · ...</div>
    <div class="watermark-line">品牌名 · KEYWORD · 品牌名 · KEYWORD · ...</div>
    <!-- 重复 8~10 行，奇偶行中英文交替，错位感更强 -->
  </div>
</div>
```

要点：
- `top:-10%;left:-10%;width:120%;height:120%` 确保旋转后无白边
- `gap:80px` 控制行间距，太密影响阅读，太疏防伪效果弱
- 透明度 `.045`（约 4.5%），肉眼几乎不可见但截图放大可辨识
- 奇偶行中英文交替排列，增加辨识难度

### 第二层：中央大号印章水印（内容层，z-index:2）

浮在内容中央的半透明大字印章，声明原创身份。

```css
.seal{
  position:absolute;left:50%;top:52%;z-index:2;
  transform:translate(-50%,-50%) rotate(-18deg);
  pointer-events:none;text-align:center;
}
.seal .seal-label{
  font-size:14px;color:rgba(212,178,106,.18);letter-spacing:6px;
  text-align:center;margin-bottom:4px;
}
.seal .seal-code{
  font-family:"Noto Serif SC",serif;font-weight:900;
  font-size:42px;color:rgba(212,178,106,.14);letter-spacing:8px;
  text-align:center;
}
.seal .seal-sub{
  font-family:"Cormorant Garamond",serif;font-style:italic;font-weight:600;
  font-size:16px;color:rgba(212,178,106,.18);letter-spacing:6px;
  text-align:center;margin-top:4px;
}
```

```html
<div class="seal">
  <div class="seal-label">平 台 名</div>
  <div class="seal-code">创作者名称</div>
  <div class="seal-sub">ORIGINAL CONTENT</div>
</div>
```

要点：
- 三行结构：平台名（小字）→ 创作者名（大字核心）→ 英文声明（小字装饰）
- 透明度 `.14~.18`，能看清但不遮挡数据阅读
- `rotate(-18deg)` 斜角，避免与表格线条平行，视觉上更像印章
- `pointer-events:none` 不影响交互
- 位置 `top:52%` 微调偏下，避开标题区，落在数据表中央

### 双层叠加规则

- 底层（z-index:1）：全页斜排重复文字，极低透明度，防裁切盗用
- 中层（z-index:2）：中央印章水印，稍高透明度，声明原创身份
- 内容层（z-index:2+）：表格数据正常显示，水印不干扰阅读
- 印章水印不得遮挡底部建议/结论区域的关键文字，必要时调整 `top` 值上移

## 组件

- 圆角卡片：`border-radius:24-28px`，金色边框，暗色渐变背景
- 胶囊标签：`border-radius:26px`，金色半透明边框 + 内发光
- 虚线框：引用/总结区域，`1px dashed rgba(212,178,106,.35)`
- 编号标记：金色径向渐变圆 + 罗马数字（Ⅰ Ⅱ Ⅲ）

## 每页底部三件套（必备）

底部预留至少 120px 安全区：

```html
<div class="disclaimer">数据获取 {YYYY.MM.DD} · 本内容仅作信息分享，不构成任何投资建议；如有侵权请联系删除</div>
<div class="watermark">@纳指心理按摩师 制图</div>
<div class="page-num">01 / 05</div>
```

```css
.disclaimer{position:absolute;left:140px;right:140px;bottom:22px;text-align:center;font-size:13px;color:rgba(207,214,228,.55);z-index:3}
.watermark{position:absolute;left:80px;bottom:82px;color:var(--muted);font-size:24px;letter-spacing:5px;font-family:"Cormorant Garamond",serif;font-style:italic;z-index:2}
.page-num{position:absolute;right:80px;bottom:78px;font-family:"DM Serif Display",serif;color:var(--gold);font-size:28px;letter-spacing:4px;z-index:2}
```

## 文字不重叠铁律

> 这是本 skill 最重要的约束。生成完每页必须截图自检，违反任何一条都要修复后重截。

1. 内容严格在 1440px 内，不允许溢出
2. 底部 120px 安全区只允许 disclaimer / watermark / page-num
3. 任何 `position:absolute` 元素必须显式声明 `z-index`（装饰 ≤1，内容 2，底部 3）
4. 不允许两个 absolute 元素的 bbox 重叠
5. 内容溢出时优先缩小 `padding > gap > font-size > 删装饰 > 拆页`，禁止隐藏内容
6. 多列布局必须用 grid 或 flex，禁止用 absolute 拼
7. 长文本必须 ellipsis 兜底：
   ```css
   .nm{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
   ```
8. 截图后逐页核对：是否文字相互覆盖、是否被底部三件套遮挡、是否被 1440 截断
9. 防伪印章水印（`.seal`）不得遮挡底部建议/结论区域的关键文字，必要时调整 `top` 值上移
10. 防伪水印和印章的 `z-index` 必须低于内容层，确保数据文字始终可读

## 截图

用项目根目录的通用脚本，**在根目录执行**：

```bash
node shot.js {topic_folder}                    # 截该目录下所有 .html
node shot.js {topic_folder}/{PREFIX}.html      # 只截单个文件
```

脚本行为（无需改动，也不要复制副本到 topic 目录）：

- 自动遍历 HTML 内所有 `<div class="card">` 节点逐张截图
- 单卡输出 `{PREFIX}.png`，多卡输出 `{PREFIX}_01.png` / `_02.png` ...
- `deviceScaleFactor: 2` → 最终 2160×2880
- 已内置 `document.fonts.ready` 等待（上限 10 秒）+ 800ms 兜底延时，确保 web font 生效

## 配套小红书文案

每个项目都需要一份 `小红书文案.md`，结构如下：

```markdown
# {主题} · 小红书文案

## 标题候选（每组 10 个，长度 ≤ 20 字）

### A · 反差 / 悬念风
1~10. ...

### B · 数据 / 事实风
1~10. ...

### C · 个人视角 / 故事风
1~10. ...

---

## 正文

{正文}

#话题1 #话题2 #话题3 #话题4 #话题5
```

### 标题规则

- 长度 ≤ 20 字（全角符号、空格按 1 字算），共 30 个候选（A/B/C 各 10）
- 三组风格内部一致、组间明显区分
- 至少 5 个含具体数字 / 名字 / 事实
- 分隔符用 `｜` 或 `·`，不要用 `|` 或 `-`
- 禁止 emoji
- 禁用词：暴涨 / 翻倍 / 稳赚 / 必涨 / 抄底 / 闭眼买 / 必看 / 一定 / 绝对 / 100% / 神器

### 正文规则

- 第一人称，每段 1~3 行，段间空行
- 长度 400~700 字
- 禁止 emoji
- 「我的观察」每条必须有具体数字或名词，禁止「值得关注」「拭目以待」类套话
- 至少 1 条独立解读，不只复述事实
- 反差点用 `←` 注释
- **禁止任何「数据来源」「数据更新于 XXXX-XX-XX」类标注**（这种元信息只放卡片 disclaimer，不放正文）
- 风险提示仅在投资 / 健康 / 法律等需要免责的题材加，普通题材不加

### 话题标签

3~5 个，按 `大类 → 主题 → 品牌/主体 → 场景 → 数字/代码` 顺序排，过多会被算法降权。
