"""Caption-anchored source crops; no generated pixels or benchmark regions."""
import fcntl
from functools import lru_cache
import hashlib
import json
import math
import re
import subprocess
import xml.etree.ElementTree as ET

from .corpus import CACHE, ROOT, page_image, source_pdf


@lru_cache(maxsize=1)
def layout_lines():
    path=CACHE/'visual-bbox.html'
    if not path.exists():
        CACHE.mkdir(parents=True,exist_ok=True)
        subprocess.run(['pdftotext','-bbox-layout',str(source_pdf()),str(path)],check=True,capture_output=True)
    raw=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',path.read_text())
    ns={'x':'http://www.w3.org/1999/xhtml'}
    result={}
    for p,page in enumerate(ET.fromstring(raw).findall('.//x:page',ns),1):
        result[p]=[{'text':' '.join(w.text or '' for w in line.findall('x:word',ns)),
                    'bbox':[float(line.attrib[a]) for a in ('xMin','yMin','xMax','yMax')]}
                   for line in page.findall('.//x:line',ns)]
    return result


def crop_bounds(record, lines):
    """Conservative full/half-column region through source or next caption.

    Bounds are inferred from source layout, never evaluator gold. Ambiguous or
    tiny regions fall back to the original full page. These are not claimed to
    be pixel-perfect object outlines.
    """
    _,_,width,height=record['bbox']
    caption=record.get('caption_bbox')
    if record['kind']=='page' or not caption:return list(record['bbox'])
    x1,y1,x2,y2=caption
    if x2<=width*.51 and x1<width*.40:
        left,right=width*.045,width*.515
    elif x1>=width*.49 and x2>width*.60:
        left,right=width*.485,width*.96
    else:left,right=width*.035,width*.965
    bottom=height-18
    starts=[];sources=[]
    for line in lines:
        bx1,by1,bx2,by2=line['bbox'];center=(bx1+bx2)/2
        if not left<=center<=right or by1<=y2+24:continue
        if re.match(r'^(Figure|Table)\s+[ABO\d][\d.]*\d',line['text']):starts.append(by1-5)
        if re.match(r'^Sources?:',line['text'],re.I):sources.append(by2+8)
    if starts:bottom=min(bottom,min(starts))
    if sources:
        inside=[s for s in sources if s<bottom]
        if inside:bottom=min(inside)
    top=max(0,y1-8)
    if bottom-top<70 or right-left<100:return list(record['bbox'])
    return [round(left,3),round(top,3),round(right,3),round(bottom,3)]


def object_image(record, dpi=180):
    bounds=crop_bounds(record,layout_lines().get(record['page'],[]))
    if bounds==record['bbox']:
        return page_image(record['page']),{'bbox':bounds,'crop_method':'full-page-fallback','evidence_id':record['id']}
    if not re.fullmatch(r'[A-Za-z0-9.-]+',record['id']):raise ValueError('Invalid evidence ID')
    suffix=hashlib.sha256(json.dumps([bounds,dpi]).encode()).hexdigest()[:10]
    path=CACHE/f"{record['id']}-crop-{suffix}.jpg"
    scale=dpi/72
    x,y=math.floor(bounds[0]*scale),math.floor(bounds[1]*scale)
    w,h=math.ceil((bounds[2]-bounds[0])*scale),math.ceil((bounds[3]-bounds[1])*scale)
    with path.with_suffix('.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if not path.exists():
            subprocess.run(['pdftoppm','-f',str(record['page']),'-l',str(record['page']),'-singlefile',
                            '-r',str(dpi),'-x',str(x),'-y',str(y),'-W',str(w),'-H',str(h),
                            '-jpeg','-jpegopt','quality=95',str(source_pdf()),str(path.with_suffix(''))],
                           check=True,capture_output=True)
    return path,{'bbox':bounds,'crop_method':'caption-column-source-boundary','evidence_id':record['id'],'dpi':dpi}
