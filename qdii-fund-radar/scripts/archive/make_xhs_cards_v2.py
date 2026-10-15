from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
ROOT=Path(__file__).parent; OUT=ROOT/'xhs_cards_v2'; OUT.mkdir(exist_ok=True)
W,H=1242,1660; bg='#f6f0e5'; brown='#3b2419'; red='#a4472c'; line='#c9a991'; white='#fffdf7'
fp=str(ROOT/'fonts/STHeiti-Medium.ttc')
def F(n): return ImageFont.truetype(fp,n)
def tx(d,p,s,n,c=brown,anchor=None): d.text(p,s,font=F(n),fill=c,anchor=anchor)
def wrap(d,x,y,s,n,maxw,leading=1.45,c=brown):
    line=''; yy=y
    for ch in s:
        if d.textbbox((0,0),line+ch,font=F(n))[2]>maxw and line: tx(d,(x,yy),line,n,c); yy+=int(n*leading); line=ch
        else: line+=ch
    if line: tx(d,(x,yy),line,n,c)
def make():
    im=Image.new('RGB',(W,H),bg); d=ImageDraw.Draw(im)
    # subtle paper grain and header
    for x in range(0,W,23): d.line((x,0,x,H),fill='#f3ecdf',width=1)
    d.line((52,112,350,112),fill=line,width=2); d.line((892,112,1190,112),fill=line,width=2)
    tx(d,(621,86),'QDII 基金雷达 · 数据分享笔记',30,brown,'mm'); tx(d,(370,86),'•',28,red,'mm'); tx(d,(872,86),'•',28,red,'mm')
    return im,d
def strip(d,xy,s,fs=34):
    x,y,w,h=xy; pts=[(x,y+8),(x+w-18,y),(x+w-8,y+h//2),(x+w-18,y+h),(x,y+h-8)]
    d.polygon(pts,fill=red); tx(d,(x+28,y+h//2),s,fs,'#fffaf0','lm')
def paper(d,xy):
    x,y,w,h=xy; d.rounded_rectangle((x,y,x+w,y+h),18,fill=white,outline='#eadfce',width=2); d.line((x+34,y+h-10,x+w-42,y+h-10),fill='#e1d4c2',width=2)
def shot(name,box):
    im=Image.open(ROOT/name).convert('RGB'); im.thumbnail((box[2]-box[0]-30,box[3]-box[1]-30)); return im
def footer(d,n):
    d.line((52,1530,470,1530),fill=line,width=2); d.line((772,1530,1190,1530),fill=line,width=2)
    tx(d,(621,1530),f'{n:02d}/05',28,red,'mm'); tx(d,(621,1590),'仅供信息整理与参考，不构成投资建议',20,'#755f52','mm')
def add(name,title,sub,body, n, img=None):
    im,d=make(); tx(d,(68,205),title,62,brown); tx(d,(68,285),sub,34,red)
    if body: wrap(d,80,375,body,32,1060)
    if img:
        x,y,w,h=img[1]; paper(d,(x,y,w,h)); sim=shot(img[0],(x,y,x+w,y+h)); im.paste(sim,(x+(w-sim.width)//2,y+(h-sim.height)//2))
    footer(d,n); im.save(OUT/name)

add('01-cover.png','QDII 基金雷达','给想了解海外基金的人', '查限额、看市场、跟踪阶段收益率\n一次对话，整理出一份可读的基金信息卡。',1)
im=Image.open(OUT/'01-cover.png'); d=ImageDraw.Draw(im); strip(d,(80,620,390,92),'一个开源 Agent Skill',34); paper(d,(85,770,1070,380)); tx(d,(145,855),'支持 Codex / Claude Code / Workbuddy / Trae',30); tx(d,(145,930),'把重复的信息检索，交给 Agent 完成。',30); tx(d,(145,1010),'你负责提问，它负责整理。',30,red); tx(d,(1080,1120),'↗',54,red,'mm'); im.save(OUT/'01-cover.png')
add('02-query.png','先查清楚，再做判断','一问，四类信息', '输入基金名称或代码，可以查询申购状态、单日限额、近一年收益率，以及季度市场分布。',2,('screenshot-1.png',(90,650,1060,720)))
add('03-quota.png','限额会变化','别再靠旧截图判断', '支持批量查看限大额、暂停申购、不限额等状态；结果带查询时间，方便后续复核。',3,('screenshot-5.png',(90,650,1060,720)))
add('04-push.png','不想每天手动查？','目前支持飞书定时推送', '设置固定时间后，自动生成限购日报，把“今天有什么变化”推送到群里。',4,('screenshot-2.png',(90,610,1060,790)))
add('05-content.png','把数据变成内容','适合做自媒体的可视化素材', '从收益率排行到持仓分析、市场分布与季度复盘，都可以进一步整理成好看的信息卡片。',5,('screenshot-3.png',(90,575,1060,440)))
im=Image.open(OUT/'05-content.png'); d=ImageDraw.Draw(im); strip(d,(90,1080,390,92),'安装方式',34); paper(d,(90,1210,1060,190)); tx(d,(125,1270),'直接告诉你的 Agent：',27); tx(d,(125,1320),'安装这个 Skill：github.com/hangliuc/qdii-fund-radar',23,red); im.save(OUT/'05-content.png')
print('\n'.join(str(p) for p in sorted(OUT.glob('*.png'))))
