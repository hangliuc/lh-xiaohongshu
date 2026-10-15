from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / 'xhs_cards'
OUT.mkdir(exist_ok=True)
W, H = 1242, 1660
navy, coral, ink, paper, blue = '#12233f', '#ef5b55', '#1b2430', '#f8f4eb', '#dce8f5'
font_path = str(ROOT / 'fonts' / 'STHeiti-Medium.ttc')
def f(size): return ImageFont.truetype(font_path, size)
def base():
    bg = Image.open(ROOT/'assets-bg.png').convert('RGB').resize((W,H))
    bg = Image.blend(bg, Image.new('RGB',(W,H),paper), .35)
    return bg
def text(draw, xy, s, size, fill=ink, anchor=None): draw.text(xy, s, font=f(size), fill=fill, anchor=anchor)
def wrap(draw, x, y, s, size, maxw, fill=ink, leading=1.45):
    words=list(s); line=''; yy=y
    for ch in words:
        test=line+ch
        if draw.textbbox((0,0),test,font=f(size))[2] > maxw and line:
            text(draw,(x,yy),line,size,fill); yy += int(size*leading); line=ch
        else: line=test
    if line: text(draw,(x,yy),line,size,fill)
    return yy+int(size*leading)
def label(draw, s, x=78, y=70):
    text(draw,(x,y),s,25,coral)
def footer(draw, n):
    draw.line((78,1550,1164,1550),fill='#c8c2b8',width=2)
    text(draw,(78,1580),'QDII FUND RADAR  ·  信息工具分享',20,navy)
    text(draw,(1164,1580),f'{n:02d} / 05',20,navy,'ra')
def shot(name, box):
    im=Image.open(ROOT/name).convert('RGB'); im.thumbnail((box[2]-box[0],box[3]-box[1]))
    x=box[0]+(box[2]-box[0]-im.width)//2; y=box[1]+(box[3]-box[1]-im.height)//2
    layer=Image.new('RGB',(box[2]-box[0],box[3]-box[1]),'white'); layer.paste(im,(x-box[0],y-box[1])); return layer

# 1 cover
im=base(); d=ImageDraw.Draw(im); label(d,'A SMALL TOOL FOR QDII DATA')
text(d,(78,210),'QDII 基金雷达',78,navy); text(d,(78,315),'把限额、市场与收益率\n放进一次对话里',50,ink)
d.rounded_rectangle((78,520,1164,740),28,fill=navy); text(d,(125,575),'查限额  ·  看分布  ·  跟踪阶段收益',34,'white'); text(d,(125,650),'让基金信息检索更快，也更适合做成内容。',27,'#dce8f5')
text(d,(78,850),'一个开源 Agent Skill',31,coral); wrap(d,78,920,'支持在 Codex、Claude Code、Workbuddy、Trae 等 Agent 中安装使用。',32,1000)
text(d,(78,1280),'数据仅供信息参考，不构成投资建议',24,'#687282'); footer(d,1); im.save(OUT/'01-cover.png')

# 2 capability screenshot 1
im=base(); d=ImageDraw.Draw(im); label(d,'01 · 查询能力'); text(d,(78,150),'你可以直接问它：',52,navy)
wrap(d,78,245,'这只 QDII 现在还能不能买？单日限额是多少？近一年表现如何？资金主要投向哪些市场？',34,1080)
d.rounded_rectangle((78,500,1164,1380),24,fill='white',outline='#d8d2c8',width=3)
im.paste(shot('screenshot-1.png',(94,516,1148,1365)),(94,516)); text(d,(78,1415),'示例：一次查询，返回申购状态、限额、收益率与市场分布。',25,ink); footer(d,2); im.save(OUT/'02-query.png')

# 3 quota screenshot 5
im=base(); d=ImageDraw.Draw(im); label(d,'02 · 限额追踪'); text(d,(78,150),'限额会变，信息要及时',52,navy)
wrap(d,78,245,'支持批量查看“限大额 / 暂停申购 / 不限额”等状态，也可以按基金代码查询。',32,1060)
d.rounded_rectangle((78,500,1164,1380),24,fill='white',outline='#d8d2c8',width=3)
im.paste(shot('screenshot-5.png',(94,516,1148,1365)),(94,516)); text(d,(78,1415),'截图中的具体数字会随平台与日期变化，请以实时查询为准。',24,ink); footer(d,3); im.save(OUT/'03-quota.png')

# 4 scheduled push + social content
im=base(); d=ImageDraw.Draw(im); label(d,'03 · 自动推送 + 内容生产'); text(d,(78,145),'不想每天手动查？',48,navy)
d.rounded_rectangle((78,255,1164,610),24,fill=navy); text(d,(120,320),'定时推送',43,'white'); wrap(d,120,405,'目前支持飞书：定时生成限购日报，直接推送到群里。',29,950,'#dce8f5')
im.paste(shot('screenshot-2.png',(78,680,1164,1300)),(78,680)); text(d,(78,1350),'把“今天有什么变化”变成固定节奏的提醒。',26,ink); footer(d,4); im.save(OUT/'04-push.png')

# 5 beautiful UI cards + install
im=base(); d=ImageDraw.Draw(im); label(d,'04 · 做自媒体'); text(d,(78,145),'把数据变成好看的卡片',48,navy)
wrap(d,78,235,'查询结果不仅能看，也能整理成适合分享的榜单、持仓分析和季度复盘。',30,1080)
im.paste(shot('screenshot-3.png',(78,485,1164,1010)),(78,485)); im.paste(shot('screenshot-4.png',(78,1035,1164,1355)),(78,1035))
text(d,(78,1395),'安装：直接告诉你的 Agent 安装这个 Skill：',25,ink)
text(d,(78,1435),'github.com/hangliuc/qdii-fund-radar/.../SKILL.md',22,navy)
footer(d,5); im.save(OUT/'05-install.png')

print('\n'.join(str(p) for p in sorted(OUT.glob('*.png'))))
