# -*- coding: utf-8 -*-
"""v3 — ויקיפדיה/ויקישיתוף בלבד.
Bing נזרק: הוא החזיר תמונות שאין להן שום קשר לשאילתה (עוף מטוגן, אנימה, פסלים).
כאן הזהות מובטחת: התמונה נלקחת מתוך הערך של אותו רב, או מקטגוריה על שמו."""
import os, re, io, json, time, hashlib, urllib.parse, urllib.request
from PIL import Image

OUT = 'candidates'
A3_LONG, A3_SHORT = 2480, 1754
MIN_LONG, MIN_SHORT = 900, 600     # רצפה נמוכה — עדיף נכון וקטן מאשר גדול ולא נכון
UA = 'RabbiPhotoFetch/1.0 (contact: 6742853@gmail.com)'
SKIP = re.compile(r'(commons-logo|wikiquote|wikisource|wikidata|icon|flag|'
                  r'edit-|ambox|question|disambig|crystal|symbol|nuvola|'
                  r'emblem|coat[_ ]of[_ ]arms|p_vip|gnome|folder|logo|'
                  r'\.svg$|\.ogg$|\.webm$)', re.I)


def bad(u):
    return bool(SKIP.search(urllib.parse.unquote(u).rsplit('/', 1)[-1]))


def get(url, timeout=45):
    req = urllib.request.Request(url)
    req.add_header('User-Agent', UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def japi(api, params):
    params.update({'format': 'json', 'formatversion': '2'})
    u = api + '?' + urllib.parse.urlencode(params)
    return json.loads(get(u).decode())


def imageinfo(api, titles):
    """מביא URL וגודל לרשימת קבצים."""
    out = []
    for i in range(0, len(titles), 25):
        chunk = titles[i:i + 25]
        try:
            d = japi(api, {'action': 'query', 'titles': '|'.join(chunk),
                           'prop': 'imageinfo',
                           'iiprop': 'url|size|extmetadata'})
            for p in d.get('query', {}).get('pages', []):
                for ii in (p.get('imageinfo') or []):
                    if not ii.get('url') or bad(ii['url']):
                        continue
                    lic = (ii.get('extmetadata', {}).get('LicenseShortName', {})
                           .get('value', ''))
                    out.append({'url': ii['url'], 'w': ii.get('width', 0),
                                'h': ii.get('height', 0),
                                'license': re.sub('<[^>]+>', '', lic)[:50],
                                'page': p.get('title', '')[:80]})
        except Exception as e:
            print('   imageinfo err:', str(e)[:70])
    return out


def from_article(api, query):
    """מוצא את הערך של הרב ומחזיר את כל התמונות שבתוכו."""
    res = []
    try:
        d = japi(api, {'action': 'query', 'list': 'search',
                       'srsearch': query, 'srlimit': 3})
        titles = [s['title'] for s in d.get('query', {}).get('search', [])]
    except Exception as e:
        print('   search err:', str(e)[:70])
        return res
    for t in titles[:2]:
        print('   ערך:', t)
        try:
            d = japi(api, {'action': 'query', 'titles': t, 'prop': 'images',
                           'imlimit': 40})
            files = []
            for p in d.get('query', {}).get('pages', []):
                files += [im['title'] for im in (p.get('images') or [])]
            files = [f for f in files if not bad(f)]
            for c in imageinfo(api, files):
                c['src'] = api.split('//')[1].split('.')[0] + ':' + t[:40]
                res.append(c)
        except Exception as e:
            print('   images err:', str(e)[:70])
    return res


def from_commons_category(query):
    """קטגוריה בוויקישיתוף על שם הרב — כל התמונות שבה."""
    api = 'https://commons.wikimedia.org/w/api.php'
    res = []
    try:
        d = japi(api, {'action': 'query', 'list': 'search',
                       'srsearch': 'incategory:"%s" OR %s' % (query, query),
                       'srnamespace': 6, 'srlimit': 25})
        files = [s['title'] for s in d.get('query', {}).get('search', [])]
        for c in imageinfo(api, files):
            c['src'] = 'commons'
            res.append(c)
    except Exception as e:
        print('   commons err:', str(e)[:70])
    return res


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
        print('\n=== %s' % name)
        cands = []
        for q in t['queries']:
            print('  q:', q)
            cands += from_article('https://he.wikipedia.org/w/api.php', q)
            cands += from_article('https://en.wikipedia.org/w/api.php', q)
            cands += from_commons_category(q)
            time.sleep(0.8)
        seen, kept = set(), []
        cands.sort(key=lambda c: -(c['w'] * c['h']))
        for c in cands:
            if c['url'] in seen or len(kept) >= 6:
                continue
            seen.add(c['url'])
            lo, sh = max(c['w'], c['h']), min(c['w'], c['h'])
            if lo < MIN_LONG or sh < MIN_SHORT:
                continue
            try:
                b = get(c['url'], timeout=60)
                im = Image.open(io.BytesIO(b))
                if im.mode not in ('RGB', 'L', 'RGBA', 'P'):
                    continue
                ext = '.png' if (im.format or '').lower() == 'png' else '.jpg'
                fn = '%02d%s' % (len(kept) + 1, ext)
                open(os.path.join(d, fn), 'wb').write(b)
                c['file'] = fn
                c['bytes'] = len(b)
                c['a3'] = lo >= A3_LONG and sh >= A3_SHORT
                kept.append(c)
                print('    v %s %dx%d %s [%s]' % (fn, c['w'], c['h'],
                      'A3' if c['a3'] else '', c['src'][:34]))
            except Exception as e:
                print('    x', str(e)[:60])
        if not kept:
            print('    -- לא נמצא כלום')
        manifest.append({'name': name, 'slug': sl, 'candidates': kept})
    json.dump(manifest, io.open(os.path.join(OUT, 'manifest.json'), 'w',
                                encoding='utf-8'), ensure_ascii=False, indent=1)
    got = sum(1 for m in manifest if m['candidates'])
    a3 = sum(1 for m in manifest if any(c['a3'] for c in m['candidates']))
    print('\n=== %d/%d עם תמונה · %d מהן בגודל A3' % (got, len(manifest), a3))


if __name__ == '__main__':
    main()
