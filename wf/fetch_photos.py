# -*- coding: utf-8 -*-
"""רץ על GitHub Actions (אינטרנט חופשי, בלי נטפרי).
מחפש תמונות ברזולוציה גבוהה לכל רב. v2 — Bing + Wikimedia + Openverse,
והגודל נמדד בפועל עם PIL ולא לפי מטא-דאטה."""
import os, re, io, json, time, hashlib, urllib.parse, urllib.request
from PIL import Image

OUT = 'candidates'
A3_LONG, A3_SHORT = 2480, 1754        # A3 ב-150dpi
MIN_LONG, MIN_SHORT = 1400, 1000      # רצפה: גם שיפור חלקי שווה שמירה
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36')


def get(url, timeout=40, headers=None):
    req = urllib.request.Request(url)
    req.add_header('User-Agent', UA)
    req.add_header('Accept-Language', 'he,en;q=0.8')
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def bing(query, limit=30):
    """גריפת Bing Images — עובד מ-IP של datacenter, בניגוד ל-DDG."""
    urls = []
    for qft in ('+filterui:imagesize-wallpaper', '+filterui:imagesize-large', ''):
        try:
            u = ('https://www.bing.com/images/search?q=' + urllib.parse.quote(query) +
                 '&qft=' + urllib.parse.quote(qft) + '&form=IRFLTR&first=1')
            h = get(u).decode('utf-8', 'replace')
            for m in re.finditer(r'murl&quot;:&quot;(.*?)&quot;', h):
                urls.append(m.group(1).replace('\\/', '/'))
            for m in re.finditer(r'"murl":"(.*?)"', h):
                urls.append(m.group(1).replace('\\/', '/'))
        except Exception as e:
            print('   bing err:', str(e)[:60])
        time.sleep(1)
        if len(urls) >= limit:
            break
    out, seen = [], set()
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append({'url': u, 'src': 'bing', 'license': '', 'page': ''})
    return out[:limit]


def wikimedia(query, limit=12):
    out = []
    for api in ('https://commons.wikimedia.org/w/api.php',
                'https://he.wikipedia.org/w/api.php'):
        try:
            u = (api + '?action=query&generator=search&gsrsearch=' +
                 urllib.parse.quote(query) +
                 '&gsrnamespace=6&gsrlimit=%d&prop=imageinfo' % limit +
                 '&iiprop=url|size|extmetadata&format=json')
            d = json.loads(get(u).decode())
            for p in (d.get('query', {}).get('pages', {}) or {}).values():
                ii = (p.get('imageinfo') or [{}])[0]
                if ii.get('url'):
                    lic = (ii.get('extmetadata', {}).get('LicenseShortName', {})
                           .get('value', ''))
                    out.append({'url': ii['url'], 'src': 'wikimedia',
                                'license': re.sub('<[^>]+>', '', lic)[:50],
                                'page': p.get('title', '')[:70]})
        except Exception as e:
            print('   wikimedia err:', str(e)[:60])
    return out


def openverse(query, limit=15):
    try:
        u = ('https://api.openverse.org/v1/images/?q=' + urllib.parse.quote(query) +
             '&page_size=%d' % limit)
        d = json.loads(get(u).decode())
        return [{'url': r['url'], 'src': 'openverse',
                 'license': r.get('license', ''), 'page': r.get('title', '')[:70]}
                for r in d.get('results', []) if r.get('url')]
    except Exception as e:
        print('   openverse err:', str(e)[:60])
        return []


def slug(name):
    return hashlib.md5(name.encode('utf-8')).hexdigest()[:8]


def main():
    targets = json.load(io.open('targets.json', encoding='utf-8'))
    os.makedirs(OUT, exist_ok=True)
    manifest = []
    for t in targets:
        name = t['name']
        sl = slug(name)
        d = os.path.join(OUT, sl)
        os.makedirs(d, exist_ok=True)
        print('\n=== %s (%s)' % (name, sl))
        cands = []
        for q in t['queries']:
            print('  q:', q)
            cands += bing(q)
            cands += wikimedia(q)
            cands += openverse(q)
            time.sleep(1)
        seen, measured = set(), []
        for c in cands:
            if not c['url'] or c['url'] in seen or len(measured) >= 40:
                continue
            seen.add(c['url'])
            try:
                b = get(c['url'], timeout=35)
                if len(b) < 60000:
                    continue
                im = Image.open(io.BytesIO(b))
                w, h = im.size
                lo, sh = max(w, h), min(w, h)
                if lo < MIN_LONG or sh < MIN_SHORT:
                    continue
                c.update({'w': w, 'h': h, 'bytes': len(b), 'data': b,
                          'a3': lo >= A3_LONG and sh >= A3_SHORT,
                          'fmt': (im.format or '').lower()})
                measured.append(c)
            except Exception:
                continue
        measured.sort(key=lambda c: -(c['w'] * c['h']))
        kept = []
        for c in measured[:5]:
            ext = '.png' if c['fmt'] == 'png' else '.jpg'
            fn = '%02d%s' % (len(kept) + 1, ext)
            open(os.path.join(d, fn), 'wb').write(c.pop('data'))
            c['file'] = fn
            kept.append(c)
            print('    v %s %dx%d %.1fMB [%s]%s' % (fn, c['w'], c['h'],
                  c['bytes'] / 1048576, c['src'], ' A3' if c['a3'] else ''))
        if not kept:
            print('    -- אין מועמד מתאים')
        manifest.append({'name': name, 'slug': sl, 'candidates': kept})
    json.dump(manifest, io.open(os.path.join(OUT, 'manifest.json'), 'w',
                                encoding='utf-8'), ensure_ascii=False, indent=1)
    n3 = sum(1 for m in manifest if any(c['a3'] for c in m['candidates']))
    print('\n=== %d/%d רבנים עם מועמד בגודל A3' % (n3, len(manifest)))


if __name__ == '__main__':
    main()
