"""Render original vector ribbon glyphs to pyRevit PNGs; no external artwork."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]/'bim/pyrevit/PlumbingEngine.extension'
PANEL=ROOT/'PlumbingEngine.tab/Analysis.panel'
GLYPHS={
    'Extract Data': [
        ('line','ink',[(5,5),(17,5),(17,14),(7,14),(7,24)]),
        ('line','accent',[(23,9),(23,23)]),
        ('line','accent',[(18,18),(23,23),(28,18)]),
        ('line','ink',[(17,27),(29,27)]),
        ('line','ink',[(3,8),(7,8)]),('line','ink',[(4,21),(10,21)])],
    'Run Analysis': [
        ('line','ink',[(5,26),(5,6),(12,6)]),
        ('line','ink',[(5,26),(27,26)]),
        ('line','accent',[(10,21),(14,16),(19,19),(27,9)]),
        ('line','accent',[(21,9),(27,9),(27,15)]),
        ('circle','ink',(5,6,2)),('circle','ink',(5,26,2))],
    'Round Trip Test': [
        ('line','accent',[(5,11),(9,6),(23,6),(27,11)]),
        ('line','accent',[(27,5),(27,11),(21,11)]),
        ('line','ink',[(27,21),(23,26),(9,26),(5,21)]),
        ('line','ink',[(5,27),(5,21),(11,21)]),
        ('line','ink',[(12,16),(20,16)]),
        ('circle','accent',(12,16,2)),('circle','accent',(20,16,2))],
    'Native Evidence': [
        ('line','ink',[(16,3),(27,7),(26,18),(22,25),(16,29),(10,25),(6,18),(5,7),(16,3)]),
        ('line','accent',[(11,16),(15,20),(22,12)]),
        ('circle','accent',(16,7,1))],
    'Plumbing Engine': [
        ('line','ink',[(5,4),(5,12),(17,12),(17,26),(27,26)]),
        ('line','ink',[(2,7),(8,7)]),('line','ink',[(24,23),(24,29)]),
        ('line','accent',[(24,4),(20,10),(20,13),(22,15),(26,15),(28,13),(28,10),(24,4)]),
        ('circle','accent',(17,19,2))],
}


def render(glyph,dark=False):
    colors={'ink':'#DFEAF3' if dark else '#23394C','accent':'#43D7C5' if dark else '#008B80'}
    scale=12
    canvas=Image.new('RGBA',(32*scale,32*scale),(0,0,0,0))
    drawing=ImageDraw.Draw(canvas)
    svg=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="none" stroke-linecap="round" stroke-linejoin="round">']
    for shape,tone,data in GLYPHS[glyph]:
        color=colors[tone]
        if shape=='line':
            width=2.4
            points=[(x*scale,y*scale) for x,y in data]
            drawing.line(points,fill=color,width=round(width*scale),joint='curve')
            for x,y in points:
                radius=width*scale/2
                drawing.ellipse((x-radius,y-radius,x+radius,y+radius),fill=color)
            svg.append('<polyline points="{}" stroke="{}" stroke-width="{}"/>'.format(' '.join('{},{}'.format(x,y) for x,y in data),color,width))
        else:
            x,y,r=data
            drawing.ellipse(((x-r)*scale,(y-r)*scale,(x+r)*scale,(y+r)*scale),fill=color)
            svg.append('<circle cx="{}" cy="{}" r="{}" fill="{}"/>'.format(x,y,r,color))
    svg.append('</svg>')
    return canvas.resize((96,96),Image.Resampling.LANCZOS),'\n'.join(svg)+'\n'


def main():
    preview=Image.new('RGB',(1000,340),'#F4F7FA')
    draw=ImageDraw.Draw(preview)
    try:font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',17)
    except OSError:font=ImageFont.load_default()
    for i,name in enumerate(GLYPHS):
        folder=ROOT if name=='Plumbing Engine' else PANEL/(name+'.pushbutton')
        folder.mkdir(parents=True,exist_ok=True)
        for dark in (False,True):
            png,svg=render(name,dark)
            stem='icon.dark' if dark else 'icon'
            png.save(folder/(stem+'.png'))
            (folder/(stem+'.svg')).write_text(svg,encoding='utf-8')
            x=i*200+52;y=25 if not dark else 175
            if dark:draw.rectangle((i*200,160,(i+1)*200,340),fill='#1D2935')
            preview.paste(png,(x,y),png)
            draw.text((i*200+16,y+105),name,fill='#263A4C' if not dark else '#EDF5FC',font=font)
            tiny=png.resize((32,32),Image.Resampling.LANCZOS)
            preview.paste(tiny,(i*200+155,y+65),tiny)
    destination=ROOT/'ribbon-icons-preview.png'
    preview.save(destination)
    print(destination)


if __name__=='__main__':main()
