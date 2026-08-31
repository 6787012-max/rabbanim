# -*- coding: utf-8 -*-
"""רץ על GitHub Actions (אינטרנט חופשי, בלי נטפרי).
מחפש תמונות ברזולוציה גבוהה לכל רב ושומר מועמדים."""
import os, re, io, json, time, hashlib, urllib.parse, urllib.request

OUT = 'candidates'
MIN_LONG, MIN_SHORT = 2480, 1754      # A3 ב-150dpi
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/125.0 Safari/537.36')


def get(url, timeout=40, headers=None):
    req = urllib.request.Request(url)
    req.add_header('User-Agent', UA)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------- מקור 1: ויקישיתוף (API רשמי, רישוי חופשי) ----------
def wikimedia(query, limit=12):
    out = []
    for api in ('https://commons.wikimedia.org/w/api.php',
                'https://he.wikipedia.org/w/api.php'):
        try:
            u = (api + '?action=query&generator=search&gsrsearch=' +
                 urllib.parse.quote(query) +
                 '&gsrnamespace=6&gsrlimit=%d&prop=imageinfo' % limit +
                 '&iiprop=url|size|extmetadata&iiurlwidth=4000&format=json')
            d = json.loads(get(u).decode())
            for p in (d.get('query', {}).get('pages', {}) or {}).values():
                ii = (p.get('imageinfo') or [{}])[0]
                if not ii.get('url'):
                    continue
                lic = (ii.get('extmetadata', {}).get('LicenseShortName', {})
                       .get('value', ''))
                out.append({'url': ii['url'], 'w': ii.get('width', 0),
                            'h': ii.get('height', 0), 'src': 'wikimedia',
                            'license': re.sub('<[^>]+>', '', lic)[:60],
                            'page': p.get('title', '')})
        except Exception as e:
            print('   wikimedia err:', e)
    return out


# ---------- מקור 2: DuckDuckGo images ----------
def ddg(query, limit=25):
    try:
        html = get('https://duckduckgo.com/?q=' + urllib.parse.quote(query) +
                   '&iax=images&ia=images').decode('utf-8', 'replace')
        m = re.search(r'vqd=["\']?([\d-]+)', html)
        if not m:
            print('   ddg: no vqd')
            return []
        u = ('https://duckduckgo.com/i.js?l=wt-wt&o=json&q=' +
             urllib.parse.quote(query) + '&vqd=' + m.group(1) + '&f=,,,,,&p=1')
        d = json.loads(get(u, headers={'Referer': 'https://duckduckgo.com/'})
                       .decode('utf-8', 'replace'))
        out = []
        for r in d.get('results', [])[:limit]:
            out.append({'url': r.get('image'), 'w': r.get('width', 0),
                        'h': r.get('height', 0), 'src': 'ddg',
                        'license': '', 'page': r.get('title', '')[:60]})
        return out
    except Exception as e:
        print('   ddg err:', e)
        return []


def slug(name):
    return hashlib.md5(name.encode('utf-8')).hexdigest()[:8]


def main():
    targets = json.load(io.open('targets.json', encoding='utf-8'))
    os.makedirs(OUT, exist_ok=True)
    manifest = []
    for t in targets:
        name, queries = t['name'], t['queries']
        sl = slug(name)
        d = os.path.join(OUT, sl)
        os.makedirs(d, exist_ok=True)
        print('\n=== %s  (%s)' % (name, sl))
        cands = []
        for q in queries:
            print('  q:', q)
            cands += wikimedia(q)
            cands += ddg(q)
            time.sleep(1.5)
        # סינון לפי רזולוציה + הסרת כפילויות
        seen, good = set(), []
        for c in cands:
            if not c.get('url') or c['url'] in seen:
                continue
            seen.add(c['url'])
            lo, sh = max(c['w'], c['h']), min(c['w'], c['h'])
            if lo >= MIN_LONG and sh >= MIN_SHORT:
                good.append(c)
        good.sort(key=lambda c: -(c['w'] * c['h']))
        print('  מועמדים בגודל מספיק: %d (מתוך %d)' % (len(good), len(seen)))
        kept = []
        for c in good[:6]:
            try:
                b = get(c['url'], timeout=60)
                if len(b) < 40000:
                    continue
                ext = '.jpg' if b[:2] == b'\xff\xd8' else ('.png' if b[:4] == b'\x89PNG' else '')
                if not ext:
                    continue
                fn = '%02d%s' % (len(kept) + 1, ext)
                open(os.path.join(d, fn), 'wb').write(b)
                c['file'] = fn
                c['bytes'] = len(b)
                kept.append(c)
                print('    ✓ %s  %dx%d  %.1fMB  [%s]' %
                      (fn, c['w'], c['h'], len(b) / 1048576, c['src']))
            except Exception as e:
                print('    x download:', str(e)[:70])
        manifest.append({'name': name, 'slug': sl, 'candidates': kept})
    json.dump(manifest, io.open(os.path.join(OUT, 'manifest.json'), 'w',
                                encoding='utf-8'), ensure_ascii=False, indent=1)
    tot = sum(len(m['candidates']) for m in manifest)
    print('\n=== סה"כ %d מועמדים ל-%d רבנים' % (tot, len(manifest)))
    miss = [m['name'] for m in manifest if not m['candidates']]
    if miss:
        print('בלי אף מועמד:', ', '.join(miss))


if __name__ == '__main__':
    main()
