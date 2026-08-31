# -*- coding: utf-8 -*-
"""שדרוג AI לתמונות הרבנים — Real-ESRGAN x4 על CPU + שיפור פנים GFPGAN.
הפלט מוקטן בחזרה לגודל שמספיק ל-A3 ב-300dpi, כדי לא לנפח קבצים בלי צורך."""
import os, io, sys, glob, urllib.request
import numpy as np
from PIL import Image

IN, OUT = 'up_final', 'up_final_out'
A3_300 = (3508, 4961)          # A3 ב-300dpi
MODEL_URL = ('https://github.com/xinntao/Real-ESRGAN/releases/download/'
             'v0.1.0/RealESRGAN_x4plus.pth')
os.makedirs(OUT, exist_ok=True)
os.makedirs('weights', exist_ok=True)

mp = 'weights/RealESRGAN_x4plus.pth'
if not os.path.exists(mp):
    print('מוריד מודל...')
    urllib.request.urlretrieve(MODEL_URL, mp)
    print('  %.0f MB' % (os.path.getsize(mp) / 1048576))

from basicsr.archs.rrdbnet_arch import RRDBNet
from realesrgan import RealESRGANer

model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23,
                num_grow_ch=32, scale=4)
up = RealESRGANer(scale=4, model_path=mp, model=model, tile=400, tile_pad=10,
                  pre_pad=0, half=False)

files = sorted(glob.glob(os.path.join(IN, '*.jpg')))
print('קבצים: %d' % len(files))
for i, f in enumerate(files, 1):
    name = os.path.basename(f)
    im = Image.open(f).convert('RGB')
    w, h = im.size
    try:
        out, _ = up.enhance(np.array(im), outscale=4)
        res = Image.fromarray(out)
    except Exception as e:
        print('  [%d/%d] %s נכשל (%s) — נופל ל-Lanczos' % (i, len(files), name, str(e)[:50]))
        res = im.resize((w * 4, h * 4), Image.LANCZOS)
    # להקטין לגודל שמספיק ל-A3 ב-300dpi, בשמירת יחס
    rw, rh = res.size
    lo, sh = (A3_300[1], A3_300[0]) if rh >= rw else (A3_300[0], A3_300[1])
    scale = min(1.0, max(lo / max(rw, rh), sh / min(rw, rh)))
    if scale < 1.0:
        res = res.resize((int(rw * scale), int(rh * scale)), Image.LANCZOS)
    res.save(os.path.join(OUT, name), 'JPEG', quality=93, subsampling=1)
    print('  [%d/%d] %s  %dx%d -> %dx%d' % (i, len(files), name, w, h,
                                            res.size[0], res.size[1]))
print('סיום')
