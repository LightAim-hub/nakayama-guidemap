# -*- coding: utf-8 -*-
"""公式ページから 所在地・電話・営業時間・定休日 を取り込む。

地図側は電話も営業時間も0件だったが、公式 nakayaman.com の各ページには
【所在地】【電話番号】【営業時間】【定休日】が書かれている。
取り込んだ結果は tools/v2-build/official_details.json に置き、
ビルドは毎回そこから読む (ビルドのたびに公式へ取りに行かない)。
"""
import json, re, time
from playwright.sync_api import sync_playwright

MAP = 'C:/Users/paipa/nakayama-guidemap/tools/v2-build/mapdata.json'
OUT = 'C:/Users/paipa/nakayama-guidemap/tools/v2-build/official_details.json'
NL = chr(10)

FIELDS = [
    ('addr',   ['所在地']),
    ('tel',    ['電話番号', '電話', 'お問い合わせ先']),
    ('hours',  ['営業時間', '診療時間', '受付時間', '開館時間', '営業日時']),
    ('closed', ['定休日', '休診日', '休館日', '休業日']),
    ('site',   ['ホームページ', 'ＨＰ', 'HP']),
]

def parse(lines):
    got = {}
    for ln in lines:
        m = re.match(r'^【([^】]+)】\s*(.*)$', ln.strip())
        if not m:
            continue
        key, val = m.group(1).strip(), m.group(2).strip()
        val = re.sub(r'\s+', ' ', val).strip('　 ')
        if not val:
            continue
        for field, labels in FIELDS:
            if key in labels and field not in got:
                got[field] = val
    return got

def main():
    d = json.load(open(MAP, encoding='utf-8'))
    targets = [(s['name'], s['url']) for s in d['shops'] if s.get('url') and s['url'] != '#']
    result, misses = {}, []
    with sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36").new_page()
        for name, url in targets:
            try:
                r = pg.goto(url, wait_until='domcontentloaded', timeout=45000)
                code = r.status if r else 0
            except Exception as e:
                misses.append('%s 取得できず %s' % (name, str(e)[:50])); continue
            if code != 200:
                misses.append('%s HTTP %s' % (name, code)); continue
            pg.wait_for_timeout(1500)
            txt = pg.evaluate("() => document.body.innerText")
            got = parse(txt.split(NL))
            if got:
                result[name] = got
            else:
                misses.append('%s 記載なし' % name)
            print(name, sorted(got))
            time.sleep(1.4)
        br.close()
    json.dump({'source': 'https://www.nakayaman.com/ の各店ページ (2026-08-04 取得)',
               'shops': result}, open(OUT, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1, sort_keys=True)
    print(NL + '取り込めた店: %d / %d' % (len(result), len(targets)))
    print('取れなかったもの: ' + (' / '.join(misses) if misses else 'なし'))

main()
