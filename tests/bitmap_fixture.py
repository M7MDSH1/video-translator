"""Generate our own PGS image subtitle; no downloaded or user-owned media."""
import struct,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageDraw,ImageFont

def create_pgs(path):
    image=Image.new('L',(520,48));draw=ImageDraw.Draw(image)
    draw.text((8,0),'Original bitmap subtitle',font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',32),fill=1)
    rle=bytearray()
    for y in range(image.height):
        x=0
        while x<image.width:
            color=image.getpixel((x,y));count=1
            while x+count<image.width and count<63 and image.getpixel((x+count,y))==color:count+=1
            rle.extend([0,(0x80 if color else 0)|count])
            if color:rle.append(color)
            x+=count
        rle.extend([0,0])
    data=bytearray()
    def segment(t,kind,payload):
        data.extend(b'PG'+struct.pack('>IIBH',round(t*90000),0,kind,len(payload))+payload)
    def pcs(t,number,objects,state=0):
        payload=struct.pack('>HHBHBBBB',640,360,0x10,number,state,0,0,objects)
        if objects:payload+=struct.pack('>HBBHH',0,0,0,60,290)
        segment(t,0x16,payload)
    pcs(1,0,1,0x80)
    segment(1,0x17,struct.pack('>BBHHHH',1,0,60,290,520,48))
    segment(1,0x14,bytes([0,0,0,16,128,128,0,1,235,128,128,255]))
    segment(1,0x15,struct.pack('>HBB',0,0,0xc0)+(len(rle)+4).to_bytes(3,'big')+struct.pack('>HH',520,48)+rle)
    segment(1,0x80,b'')
    pcs(3,1,0);segment(3,0x80,b'')
    Path(path).write_bytes(data)

def build_fixtures():
    from videotranslator.project import new_project,save_project
    from videotranslator.engine import probe
    root=Path('projects/functional-check').resolve();root.mkdir(parents=True,exist_ok=True)
    create_pgs(root/'bitmap.sup')
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=0x345678:s=640x360:r=24:d=5','-f','lavfi','-i','sine=frequency=440:duration=5','-i',str(root/'bitmap.sup'),'-map','0:v','-map','1:a','-map','2:s','-c:v','libx264','-c:a','aac','-c:s','copy',str(root/'bitmap-pgs.mkv')],check=True)
    for codec,name in [('copy','pgs'),('dvdsub','dvd'),('dvbsub','dvb')]:
        video=root/('bitmap-'+name+'.mkv')
        if name!='pgs':subprocess.run(['ffmpeg','-v','error','-y','-fix_sub_duration','-i',str(root/'bitmap-pgs.mkv'),'-map','0','-c','copy','-c:s',codec,str(video)],check=True)
        p=new_project(video,probe(video));p.update(mode='ocr',source='en',ocr_script='en',sample_interval=.5,roi=[.03,.7,.94,.28],original_kind='track',appearance='add')
        save_project(p,root/('bitmap-'+name+'.json'))

if __name__=='__main__':build_fixtures()
