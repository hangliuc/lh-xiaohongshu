from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import random

OUT=Path(__file__).parent; OUT.mkdir(exist_ok=True)
ROOT=Path('/Users/shareit/personal/xiaohongshu/qdii-fund-radar')
SERIF=str(ROOT/'fonts/Songti.ttc'); SANS=str(ROOT/'fonts/STHeiti-Medium.ttc')
W,H=1242,1660; BG='#f4eee3'; PAPER='#fffdf8'; BROWN='#352116'; RED='#a84529'; MUTED='#8b7768'; LINE='#d8cbbb'
def F(p,n): return ImageFont.truetype(p,n)
def text(d,xy,s,n,c=BROWN,anchor=None,font=SERIF): d.text(xy,s,font=F(font,n),fill=c,anchor=anchor)
def fmt_ret(s): return f'{float(s.rstrip("%")):.2f}%'
def sort_rows(rows):
    return sorted(rows, key=lambda r: (-float(r[3]), -float(r[2].rstrip('%'))))
def base(page,title,count,paused):
    im=Image.new('RGB',(W,H),'#c9c9c7'); d=ImageDraw.Draw(im); d.rounded_rectangle((8,18,W-8,H-18),36,fill=BG)
    random.seed(20+page)
    for _ in range(15000):
        x=random.randrange(12,W-12); y=random.randrange(22,H-22); d.point((x,y),fill=random.choice(['#f2ebdf','#f7f1e7','#eee6d8']))
    d.line((52,112,360,112),fill='#bda08d',width=2); d.line((880,112,1190,112),fill='#bda08d',width=2)
    text(d,(620,88),'QDII Fund Radar',30,BROWN,'mm',SANS); d.rounded_rectangle((1080,48,1150,102),30,fill='#c9c3b9')
    d.ellipse((461,78,477,94),outline=RED,width=4); d.line((473,91,490,108),fill=RED,width=4)
    text(d,(620,170),title,61,BROWN,'mm'); text(d,(620,240),'主动管理 QDII' if page==1 else '指数基金 · C类份额',30,MUTED,'mm',SANS)
    text(d,(620,300),f'2026-09-03  ·  共 {count} 只  ·  {count-paused} 可申购  ·  {paused} 暂停中',30,RED,'mm',SANS)
    return im,d
def paper(d,x,y,w,h):
    d.rounded_rectangle((x+8,y+10,x+w+8,y+h+10),18,fill='#d6c9b8'); d.rounded_rectangle((x,y,x+w,y+h),18,fill=PAPER,outline='#e7dccd',width=2)
    d.polygon([(x+w-70,y),(x+w,y),(x+w,y+70),(x+w-35,y+55)],fill='#eee5d8'); d.line((x+w-70,y,x+w-35,y+55,x+w,y+70),fill='#dbd0c0',width=2)
def combined_table(im,d,y,active_rows,paused_rows):
    active_rows=sort_rows(active_rows); paused_rows=sort_rows(paused_rows)
    rows=[('可申购',*r) for r in active_rows]+[('暂停申购',*r) for r in paused_rows]
    h=1170; paper(d,58,y,1126,h)
    yy=y+150; d.rectangle((82,yy-70,1160,yy-17),fill='#f0e8dc'); d.line((92,yy-17,1150,yy-17),fill=RED,width=2)
    header_size=30
    for x,label,anc in [(115,'状态','mm'),(250,'基金名称 · 代码','lm'),(930,'近一年收益率','rm'),(1135,'限额','rm')]: text(d,(x,yy-43),label,header_size,BROWN,anc,SERIF)
    step=min(60,max(46,int(980/len(rows))))
    for i,(status,name,code,ret,limit) in enumerate(rows):
        if status=='暂停申购' and (i==len(active_rows)):
            d.line((92,yy+12,1150,yy+12),fill=RED,width=2)
            yy+=24
        if i%2==1: d.rectangle((82,yy-7,1160,yy+step-7),fill='#f8f3eb')
        badge_fill='#e9dfd3' if status=='可申购' else '#f2d7ce'
        d.rounded_rectangle((87,yy+step//2-17,143,yy+step//2+17),17,fill=badge_fill)
        text(d,(115,yy+step//2),'可申购' if status=='可申购' else '暂停',17,RED if status!='可申购' else MUTED,'mm',SANS)
        text(d,(250,yy+step//2),f'{name}  {code}',24,BROWN,'lm')
        text(d,(930,yy+step//2),fmt_ret(ret),25,RED,'rm',SANS); text(d,(1135,yy+step//2),limit,25,RED,'rm',SANS)
        d.line((92,yy+step-1,1150,yy+step-1),fill='#e4dbcf',width=1); yy+=step
def footer(d,page):
    text(d,(621,1590),'数据为用户提供 · 以基金公司最新公告为准',18,MUTED,'mm',SANS)
active=[('广发全球精选','021277','41.33%','10000'),('长城全球新能源车','018036','52.21%','10000'),('华夏全球科技先锋','024239','32.93%','5000'),('华宝纳斯达克精选','017437','8.27%','2000'),('华宝致远混合','008254','41%','2000'),('嘉实全球产业升级','017731','82.98%','1000'),('国富亚洲机会','021662','77.59%','1000'),('富国全球科技互联网','022184','52.25%','1000'),('银华海外数字经济','016702','26.8%','1000'),('天弘全球高端制造','016665','69.87%','500'),('汇添富全球移动互联','015202','20.28%','300'),('华夏移动互联','002891','85.28%','100'),('嘉实美国成长','000043','16.64%','100'),('国富全球科技','021842','63.55%','100'),('建信新兴市场混合','539002','95.64%','100'),('华宝海外科技','017204','29.06%','20')]
passive=[('汇添富纳斯达克100','018967','14.96%','2000'),('国泰纳斯达克100','160213','18.05%','100'),('天弘纳斯达克100','018044','17%','100'),('万家纳斯达克100','019442','17.17%','10'),('华安纳斯达克100','014978','16.76%','10'),('华泰柏瑞纳斯达克100','019525','16%','10'),('南方纳斯达克100','016453','16.73%','10'),('大成纳斯达克100','008971','16.29%','10'),('宝盈纳斯达克100','019737','16.49%','10'),('建信纳斯达克100','012752','15.86%','10'),('招商纳斯达克100','019548','16.72%','10'),('摩根纳斯达克100','019173','17.18%','10'),('广发纳斯达克100','006479','16.47%','5')]
for page,title,data,paused in [(1,'纳指主动型基金限购日报',active,4),(2,'纳指被动型基金限购日报',passive,4)]:
    im,d=base(page,title,len(data)+paused,paused); p=[('浦银安盛全球智能科技','014002','51.58%','3000'),('景顺长城纳斯达克科技','017093','29.86%','100'),('易方达全球成长精选','012922','73.89%','10'),('易方达标普信息科技','161128','23.52%','10')] if page==1 else [('华夏纳斯达克100','015300','16.38%','100'),('博时纳斯达克100','016057','17.85%','100'),('嘉实纳斯达克100','016533','16.85%','100'),('易方达纳斯达克100','012870','16.56%','10')]; combined_table(im,d,365,data,p); footer(d,page); im.save(OUT/f'{page:02d}-nasdaq-limit-daily.png')
