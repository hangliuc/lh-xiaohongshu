from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import random, math

OUT=Path(__file__).parent; ROOT=Path('/Users/shareit/personal/xiaohongshu/qdii-fund-radar')
SERIF=str(ROOT/'fonts/Songti.ttc'); SANS=str(ROOT/'fonts/STHeiti-Medium.ttc')
W,H=1242,1660; BG='#f4eee3'; CREAM='#f7f0e5'; PAPER='#fffaf1'; RED='#b84b2e'; TAN='#c7a994'; INK='#342119'; MUTED='#876f61'
def F(p,n): return ImageFont.truetype(p,n)
def tx(d,xy,s,n,c=CREAM,anchor=None,font=SERIF): d.text(xy,s,font=F(font,n),fill=c,anchor=anchor)
def centered_parts(d,y,parts,n):
    widths=[d.textbbox((0,0),s,font=F(SERIF,n))[2] for s,c in parts]
    x=(W-sum(widths))//2
    for (s,c),w in zip(parts,widths): tx(d,(x,y),s,n,c,'lm',SERIF); x+=w
def paper(d,x,y,w,h,fill=PAPER):
    d.rounded_rectangle((x+10,y+14,x+w+10,y+h+14),22,fill='#1b100c')
    d.rounded_rectangle((x,y,x+w,y+h),22,fill=fill,outline='#e3d3c2',width=2)
    d.polygon([(x+w-92,y),(x+w,y),(x+w,y+92),(x+w-44,y+70)],fill='#eee1d0')
    d.line((x+w-92,y,x+w-44,y+70,x+w,y+92),fill='#d8c8b7',width=2)
def line(d,x1,y1,x2,y2,fill=TAN,w=2): d.line((x1,y1,x2,y2),fill=fill,width=w)

im=Image.new('RGB',(W,H),BG); d=ImageDraw.Draw(im)
random.seed(903)
for _ in range(23000):
    x=random.randrange(W); y=random.randrange(H)
    d.point((x,y),fill=random.choice(['#f2ebdf','#f7f1e7','#eee6d8']))
# warm editorial header, matching the detail pages
line(d,0,112,W,112,'#a84529',2)
d.arc((500,48,560,115),180,360,fill=RED,width=5); d.arc((560,48,620,115),180,360,fill=RED,width=5)
d.line((560,78,560,132),fill=INK,width=5); d.arc((493,51,627,143),180,360,fill=RED,width=5)
tx(d,(700,82),'QDII Fund Radar',30,INK,'lm',SERIF)
tx(d,(70,82),'2026.09.03',32,MUTED,'lm',SERIF)
# small tape label
d.polygon([(84,215),(405,205),(420,273),(98,282)],fill=RED)
tx(d,(125,246),'纳指限购日报',34,CREAM,'lm')
# headline: one clear message, no fund names
centered_parts(d,390,[('纳指',RED),('限购额度',INK)],91)
tx(d,(620,535),'33只基金',112,RED,'mm')
tx(d,(620,665),'发生变化',91,INK,'mm')
line(d,250,735,992,735,'#bda08d',2)
tx(d,(620,790),'主动型 + 被动型  ·  昨日 → 今日',30,MUTED,'mm',SERIF)
# one paper card for the swipe prompt
paper(d,80,915,1082,420)
tx(d,(132,995),'想知道哪些基金变了？',36,INK,'lm')
tx(d,(132,1085),'右滑查看详情',74,RED,'lm')
tx(d,(1035,1117),'→',104,RED,'mm',SERIF)
line(d,132,1160,1110,1160,'#d8c8b7',2)
tx(d,(132,1224),'完整名单  ·  申购状态  ·  最新额度',28,MUTED,'lm',SERIF)
# minimal footer
line(d,70,1498,455,1498,'#bda08d',2); line(d,787,1498,1172,1498,'#bda08d',2)
tx(d,(620,1507),'QDII Fund Radar',19,MUTED,'mm',SERIF)
tx(d,(620,1588),'数据整理自用户提供信息 · 不构成投资建议',18,MUTED,'mm',SERIF)
im.save(OUT/'00-nasdaq-limit-cover.png')
