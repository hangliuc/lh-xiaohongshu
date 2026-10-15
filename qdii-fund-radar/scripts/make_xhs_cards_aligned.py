from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path
import random

ROOT=Path(__file__).resolve().parent
PACKAGE_ROOT=ROOT.parent
OUT=PACKAGE_ROOT/'cards'; OUT.mkdir(exist_ok=True)
ASSET_ROOT=PACKAGE_ROOT/'assets'
W,H=1242,1660
BG='#f4eee3'; PAPER='#fffdf8'; BROWN='#352116'; RED='#a84529'; MUTED='#8b7768'; GREY='#d8d0c5'
SERIF=str(PACKAGE_ROOT/'fonts/Songti.ttc'); SANS=str(PACKAGE_ROOT/'fonts/STHeiti-Medium.ttc')
CLIP_SOURCE=ASSET_ROOT/'reference-paperclip-crop.png'; CLIP_CACHE=None
def fs(path,n): return ImageFont.truetype(path,n)
def t(d,xy,s,n,c=BROWN,anchor=None,font=SERIF): d.text(xy,s,font=fs(font,n),fill=c,anchor=anchor)
def bbox(d,s,n,font=SERIF): return d.textbbox((0,0),s,font=fs(font,n))
def centered_mixed(d,y,parts,n,spacing=0):
    widths=[bbox(d,s,n)[2] for s,c in parts]; total=sum(widths)+spacing*(len(parts)-1); x=(W-total)//2
    for (s,c),w in zip(parts,widths): t(d,(x,y),s,n,c); x+=w+spacing
def wrap(d,x,y,s,n,maxw,leading=1.45,c=BROWN,font=SERIF):
    line=''; yy=y
    for ch in s:
        if bbox(d,line+ch,n,font)[2]>maxw and line: t(d,(x,yy),line,n,c,font=font); yy+=int(n*leading); line=ch
        else: line+=ch
    if line: t(d,(x,yy),line,n,c,font=font)
    return yy+n
def base(page):
    im=Image.new('RGB',(W,H),'#c9c9c7')
    d=ImageDraw.Draw(im)
    d.rounded_rectangle((8,18,W-8,H-18),36,fill=BG)
    # very light paper grain
    random.seed(13+page)
    for _ in range(18000):
        x=random.randrange(12,W-12); y=random.randrange(22,H-22)
        if random.random()<.75: d.point((x,y),fill=random.choice(['#f2ebdf','#f7f1e7','#eee6d8']))
    # top rule and chapter icon
    d.line((52,112,360,112),fill='#bda08d',width=2); d.line((880,112,1190,112),fill='#bda08d',width=2)
    d.ellipse((406,100,414,108),fill=RED); d.ellipse((828,100,836,108),fill=RED)
    draw_chapter_icon(d,page)
    t(d,(620,88),'QDII Fund Radar',30,BROWN,'mm',font=SANS)
    d.rounded_rectangle((1080,48,1150,102),30,fill='#c9c3b9'); t(d,(1115,75),f'{page}/7',24,'white','mm',font=SANS)
    return im,d
def draw_chapter_icon(d,page):
    """Small content-specific chapter mark in the same visual position as the reference umbrella."""
    c=RED; x,y=462,87
    if page in (1,2,3):
        # magnifying glass: easy query / query result
        d.ellipse((x-31,y-31,x+22,y+22),outline=c,width=7); d.line((x+11,y+12,x+40,y+41),fill=BROWN,width=7)
        if page==1: d.ellipse((x-8,y-8,x+5,y+5),fill=c)
        elif page==2: d.line((x-14,y-1,x+5,y-1),fill=c,width=5); d.line((x-14,y+11,x+10,y+11),fill=c,width=5)
        else: d.line((x-13,y-8,x+7,y-8),fill=c,width=5); d.line((x-13,y+7,x+3,y+7),fill=c,width=5)
    elif page==4:
        # checklist / limit tracker
        d.rounded_rectangle((x-28,y-36,x+28,y+36),8,outline=c,width=5); d.line((x-15,y-14,x-7,y-6,x+7,y-23),fill=c,width=5); d.line((x-15,y+9,x-7,y+17,x+7,y),fill=c,width=5); d.line((x+13,y-14,x+20,y-14),fill=BROWN,width=4); d.line((x+13,y+9,x+20,y+9),fill=BROWN,width=4)
    elif page==5:
        # notification bell
        d.arc((x-28,y-25,x+28,y+35),180,360,fill=c,width=6); d.line((x-28,y+5,x-28,y+27),fill=c,width=6); d.line((x+28,y+5,x+28,y+27),fill=c,width=6); d.line((x-34,y+27,x+34,y+27),fill=c,width=6); d.ellipse((x-7,y+28,x+7,y+41),fill=BROWN); d.ellipse((x-4,y-38,x+4,y-30),fill=c)
    elif page==6:
        # content chart / media card
        d.rounded_rectangle((x-36,y-30,x+36,y+28),8,outline=c,width=5); d.line((x-23,y+14,x-8,y-1,x+5,y+8,x+23,y-14),fill=BROWN,width=5); d.ellipse((x+18,y-23,x+28,y-13),fill=c); d.line((x-25,y+39,x+25,y+39),fill=BROWN,width=5)
    else:
        # install / link symbol
        d.arc((x-31,y-24,x+9,y+20),90,300,fill=c,width=7); d.arc((x-9,y-20,x+31,y+24),270,120,fill=c,width=7); d.line((x-8,y-3,x+8,y+3),fill=BROWN,width=6)
def ribbon(d,x,y,w,s):
    pts=[(x,y+8),(x+w-20,y),(x+w-8,y+42),(x+w-22,y+88),(x,y+82)]
    d.polygon(pts,fill=RED); t(d,(x+30,y+45),s,39,'#fff9ef','lm')
    d.line((x-20,y+12,x-2,y+2),fill=RED,width=5); d.line((x-14,y+28,x+2,y+14),fill=RED,width=5)
def paper(im,d,x,y,w,h):
    # shadow + paper + folded corner
    d.rounded_rectangle((x+8,y+12,x+w+8,y+h+12),18,fill='#d6c9b8')
    d.rounded_rectangle((x,y,x+w,y+h),18,fill=PAPER,outline='#e7dccd',width=2)
    d.polygon([(x+w-78,y),(x+w,y),(x+w,y+78),(x+w-35,y+62)],fill='#eee5d8')
    d.line((x+w-78,y,x+w-35,y+62,x+w,y+78),fill='#dbd0c0',width=2)
    paste_paperclip(im,x+12,y-18)
def paste_paperclip(im,x,y):
    """Use the actual reference screenshot's clip silhouette, isolated from its paper background."""
    global CLIP_CACHE
    if CLIP_CACHE is None:
        src=Image.open(CLIP_SOURCE).convert('RGBA')
        px=src.load()
        for yy in range(src.height):
            for xx in range(src.width):
                r,g,b,a=px[xx,yy]
                redness=max(0,r-g)
                lum=(r+g+b)//3
                if redness>15:
                    alpha=min(255,(redness-10)*12)
                elif lum<215:
                    alpha=min(180,(215-lum)*3)
                else:
                    alpha=0
                px[xx,yy]=(r,g,b,alpha)
        # The reference clip is a narrow vertical mark; preserve its proportions.
        CLIP_CACHE=src.resize((72,128),Image.Resampling.LANCZOS)
    im.paste(CLIP_CACHE,(x,y),CLIP_CACHE)
def footer(d,page):
    d.line((52,1531,465,1531),fill='#bda08d',width=2); d.line((777,1531,1190,1531),fill='#bda08d',width=2)
    d.ellipse((475,1526,484,1535),fill=RED); d.ellipse((758,1526,767,1535),fill=RED)
    t(d,(621,1535),f'{page:02d}/07',31,RED,'mm'); t(d,(621,1590),'QDII Fund Radar',18,MUTED,'mm',font=SANS)
def place_shot(im,name,box):
    x,y,w,h=box; frame=Image.new('RGB',(w,h),PAPER); src=Image.open(ASSET_ROOT/name).convert('RGB'); src.thumbnail((w-28,h-28)); frame.paste(src,((w-src.width)//2,(h-src.height)//2)); im.paste(frame,(x,y))
def card_label(im,d,x,y,num,title,sub):
    paper(im,d,x,y,490,220); d.ellipse((x+218,y+30,x+275,y+87),fill=RED); t(d,(x+246,y+58),f'{num:02d}',23,'white','mm',font=SANS); t(d,(x+245,y+125),title,35,BROWN,'mm'); d.line((x+65,y+150,x+425,y+150),fill='#cfc0b0',width=2); t(d,(x+245,y+183),sub,24,BROWN,'mm')

# 1 / 7
im,d=base(1); ribbon(d,78,218,360,'开源 Agent Skill')
centered_mixed(d,375,[('不懂代码，也能',BROWN),('轻松查询',RED)],70)
centered_mixed(d,485,[('QDII 基金信息',BROWN)],58)
paper(im,d,85,650,1070,450)
centered_mixed(d,735,[('一句话，就能开始查询',BROWN)],38)
centered_mixed(d,815,[('限额 · 市场 · 收益率 · …',RED)],37)
centered_mixed(d,895,[('后续还会持续拓展更多信息',BROWN)],33)
centered_mixed(d,990,[('Codex · CloudCode · WorkBuddy · Trae · …',BROWN)],27)
centered_mixed(d,1210,[('把复杂检索，变成简单提问。',BROWN)],37)
footer(d,1); im.save(OUT/'01-cover.png')

# 2 / 7
im,d=base(2); ribbon(d,78,218,320,'01 · 很容易查询')
centered_mixed(d,380,[('不用记指令，直接问。',BROWN)],66)
centered_mixed(d,485,[('支持多种 Agent 快速接入',RED)],31)
card_label(im,d,85,600,1,'申购状态', '暂停 / 限大额 / 不限额')
card_label(im,d,667,600,2,'单日限额', '批量查看可申购额度')
card_label(im,d,85,870,3,'近一年收益率', '最新净值与净值日期')
card_label(im,d,667,870,4,'市场分布', '季度报告中的国家 / 地区')
paper(im,d,85,1200,1070,180); centered_mixed(d,1260,[('数据有时效，请以实时查询为准。',RED)],30)
footer(d,2); im.save(OUT/'02-capabilities.png')

# 3 / 7
im,d=base(3); ribbon(d,78,218,300,'01 · 查询示例')
centered_mixed(d,380,[('一句话，整理出一份',BROWN)],58)
centered_mixed(d,455,[('可读的基金信息卡',RED)],64)
wrap(d,90,575,'输入基金名称或代码，返回申购状态、限额、收益率与市场分布。',30,1060)
paper(im,d,80,690,1080,670); place_shot(im,'screenshot-1.png',(102,712,1036,626)); paste_paperclip(im,92,672)
footer(d,3); im.save(OUT/'03-query.png')

# 4 / 7
im,d=base(4); ribbon(d,78,218,430,'01 · 申购限额查询')
centered_mixed(d,380,[('申购限额动态更新，以最新数据为准。',BROWN)],52)
wrap(d,90,505,'支持批量查看“限大额 / 暂停申购 / 不限额”等状态，并显示查询时间，便于复核。',30,1060)
paper(im,d,80,700,1080,680); place_shot(im,'screenshot-5.png',(102,722,1036,636)); paste_paperclip(im,92,682)
footer(d,4); im.save(OUT/'04-quota.png')

# 5 / 7
im,d=base(5); ribbon(d,78,218,420,'02 · 定时推送')
centered_mixed(d,380,[('申购信息，支持',BROWN),('定时同步',RED)],55)
wrap(d,90,505,'目前支持飞书定时推送：按设定时间生成限购日报，并将最新变化同步至群组。',30,1060)
paper(im,d,80,680,1080,650); place_shot(im,'screenshot-2.png',(102,702,1036,606)); paste_paperclip(im,92,662)
paper(im,d,80,1365,1080,105); centered_mixed(d,1400,[('目前支持：Feishu  ·  后续可扩展：wx · dingding · …',RED)],25)
footer(d,5); im.save(OUT/'05-push.png')

# 6 / 7 — new content module using the attached wide report image
im,d=base(6); ribbon(d,78,218,300,'03 · 做自媒体')
centered_mixed(d,380,[('把查询结果变成',BROWN),('内容资产',RED)],58)
wrap(d,90,510,'把收益率、市场分布、持仓演化、交易习惯和季度复盘，整理成适合发布的信息图。',30,1060)
paper(im,d,80,655,1080,560); place_shot(im,'screenshot-4.png',(102,695,1036,470)); paste_paperclip(im,92,637)
paper(im,d,80,1280,1080,145); centered_mixed(d,1325,[('适合复盘、分享，也适合持续更新。',BROWN)],30)
footer(d,6); im.save(OUT/'06-content-module.png')

# 7 / 7 — retain the original content example and installation card
im,d=base(7); ribbon(d,78,218,360,'03 · 原有内容示例')
centered_mixed(d,380,[('好看的卡片，也能',BROWN),('自己生成',RED)],56)
wrap(d,90,510,'从收益率排行到持仓分析、市场分布与季度复盘，都可以进一步整理成适合分享的内容。',30,1060)
paper(im,d,80,650,1080,500); place_shot(im,'screenshot-3.png',(102,672,1036,460)); paste_paperclip(im,92,632)
ribbon(d,80,1220,240,'安装方式')
paper(im,d,80,1325,1080,140); t(d,(115,1370),'直接告诉你的 Agent：安装这个 Skill',28,BROWN); t(d,(115,1415),'github.com/hangliuc/qdii-fund-radar/.../SKILL.md',22,RED,font=SANS)
footer(d,7); im.save(OUT/'07-content-install.png')
print('\n'.join(str(p) for p in sorted(OUT.glob('*.png'))))
