# -*- coding: utf-8 -*-
"""なかやま商店街マップ v2 — 実座標データセット生成 + HTML生成
入力 (スクリプトと同じフォルダ): osm_raw2.json / oq3.json / verified_shops.json /
      shops_geo_osm.json / store_addresses_geo.json / new_shops_geo.json / template.html
通常出力: mapdata.json (中間) と リポジトリ直下の index.html / v2.html
preview出力: リポジトリ直下の preview.html (本番2ファイルは非変更)
実行: python tools/v2-build/build_mapdata.py [--preview] (どこから実行してもよい)
"""
import argparse, json, math, os
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
def P(name):
    return os.path.join(HERE, name)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--preview', action='store_true', help='preview専用データとテンプレートでpreview.htmlだけを生成')
ARGS = parser.parse_args()

# リポジトリ直下 (tools/v2-build/ の2つ上)。無ければスクリプト隣に確認用HTMLを出力
_repo = os.path.abspath(os.path.join(HERE, '..', '..'))
if ARGS.preview and os.path.isdir(os.path.join(_repo, '.git')):
    OUT_HTMLS = [os.path.join(_repo, 'preview.html')]
    TEMPLATE_HTML = P('preview.template.html')
elif os.path.isdir(os.path.join(_repo, '.git')):
    OUT_HTMLS = [os.path.join(_repo, 'index.html'), os.path.join(_repo, 'v2.html')]
    TEMPLATE_HTML = P('template.html')
else:
    OUT_HTMLS = [P('v2_index.html')]
    TEMPLATE_HTML = P('preview.template.html' if ARGS.preview else 'template.html')

# 通常ビルドは、現在の本番mapdataを位置修正前の凍結ベースとして使う。
# preview側で増えた道路・信号・meta・店舗付帯情報を本番へ混ぜないための境界。
PRODUCTION_BASELINE = None
if not ARGS.preview:
    with open(P('mapdata.json'), encoding='utf-8') as f:
        PRODUCTION_BASELINE = json.load(f)
    if (len(PRODUCTION_BASELINE.get('shops', [])) != 60 or
            len(PRODUCTION_BASELINE.get('roads', [])) != 62 or
            len(PRODUCTION_BASELINE.get('signals', [])) != 13):
        raise SystemExit('production baseline guard failed: expected shops=60 roads=62 signals=13')

LAT0, LON0 = 38.2935, 140.8435
COSF = math.cos(math.radians(LAT0))
ROT = math.radians(46.4)  # バス通り(方位133.6°)を画面下向きにする時計回り回転
INFO_AS_OF = '2026年6月12日'  # 振興組合支給マップの明記日 (2026-07-10受領)

# 校章等の使用許可と正式画像の受領後にだけパスを設定する。
# 空文字の間はテンプレート側の協力ロゴ欄を表示しない。
MIYAGI_UNIVERSITY_LOGO_SRC = 'assets/myu_logo.png'

def to_m(lat, lng):
    return ((lng - LON0) * 111320 * COSF, (lat - LAT0) * 111320)

def project(lat, lng):
    mx, my = to_m(lat, lng)
    # 画面: x右 y下。北上向き→x=mx, y=-my。さらに回転ROT(時計回り)
    x0, y0 = mx, -my
    x = x0 * math.cos(ROT) - y0 * math.sin(ROT)
    y = x0 * math.sin(ROT) + y0 * math.cos(ROT)
    return (x, y)

def unproject(x, y):
    """投影後のメートル座標を緯度経度へ戻す。"""
    inv = -ROT
    x0 = x * math.cos(inv) - y * math.sin(inv)
    y0 = x * math.sin(inv) + y * math.cos(inv)
    lng = LON0 + x0 / (111320 * COSF)
    lat = LAT0 + (-y0) / 111320
    return (lat, lng)

def unproject_expr():
    """JS側 逆変換用の定数"""
    return {'lat0': LAT0, 'lon0': LON0, 'cosf': COSF, 'rot_deg': 46.4}

# ---------------- 店舗リスト構築 (2026-05-18版 紙マップ準拠) ----------------
verified = json.load(open(P('verified_shops.json'), encoding='utf-8'))
osm_matched = {r['name']: r for r in json.load(open(P('shops_geo_osm.json'), encoding='utf-8'))['matched']}
gsi_addr = {a['name']: a for a in json.load(open(P('store_addresses_geo.json'), encoding='utf-8'))}
new_geo = {a['name']: a for a in json.load(open(P('new_shops_geo.json'), encoding='utf-8'))}

DROP = {'おかきや', 'お肉とお酒のうちだ'}  # 2026-05-18版 紙マップ・公式サイトともに無し
RENAME = {  # 紙マップ(2026-05-18)表記を正とする
    '中山接骨院': '中山鍼灸接骨院',
    'サト商会': 'サトー商会',
    'cafe NAO': 'cake NAO',      # 公式ページH1「Cake NAO」・紙は cake NAO
    'ウエルシア中山店': 'ウエルシア薬局',
    'Friend.vividhair': 'Friend vividhair',
    '佐藤紀夫税理士事務所': '佐藤次夫税理士事務所',  # 紙・公式ページタイトル/H1とも「次夫」
    '中華レストランとらの子': '中華レストラン とらの子',
    'レストランKAYA': 'レストラン KAYA',
    '藤倉設備': '藤倉設備工業',
    '七十七銀行 中山支店': '七十七銀行中山支店',
    'ダイニングバー祭': 'ダイニングバー 祭',
    'Double Egg 5丁目': 'Double Egg5丁目',
    'Double Egg 4丁目': 'Double Egg4丁目',
}
RECAT = {  # 紙マップの星色・公式サイト分類に合わせる (紙優先)
    'ウジエスーパー中山店': 'food',
    'サト商会': 'food',
    '柏屋': 'life',
    'たけむらや': 'life',
    'Dogsalon Blanche': 'medical',   # 紙=白星 (拡大目視確認済)
    'ウエルシア中山店': 'life',      # 紙=緑星 (拡大目視確認済)
}
ADDR_FIX = {  # 表示住所の補正 (座標には影響しない)
    '中山郵便局': '仙台市青葉区中山6-6-3',            # 日本郵便/NAVITIME一致
    '中山市民センター': '仙台市青葉区中山3-13-1',      # 仙台市公式 (nakayaman側の3-3-1は誤記)
    'ダイシン長命ヶ丘店': '仙台市泉区南中山1-32-1',    # 南中山は泉区 (nakayaman側の青葉区は誤記)
}
# 座標の明示上書き (名寄せ誤りの補正)
COORD_OVERRIDE = {
    # Double Egg 4丁目: イートイン専門店 = 中山4丁目6-36 (公式 w-egg.jp / Yahoo!マップ)。
    # 5丁目19-5 はテイクアウト・デリバリー専門の別店舗。
    # 国土地理院 住所検索APIで号レベル一致「宮城県仙台市青葉区中山四丁目６番３６号」。
    'Double Egg 4丁目': ('gsi_addr', 38.291851, 140.842712),
    'Double Egg 5丁目': ('gsi_addr', None, None),  # None→GSI値を使う
    '志摩整骨院': ('gsi_addr', None, None),        # OSM同名ノードは西側で紙と不整合
    '中山鳥瀧不動尊（目の神様）': ('osm:exact', 38.2956402, 140.8414793),  # 平田稲荷神社と同一境内
    # みなとや: OSM同名ノードは250m東の別施設疑い。後段で振興組合掲載の1-17-4へ補正
    'みなとや': ('gsi_addr', None, None),
}

shops = []
for s in verified['STORES'] + verified['SPOTS']:
    name = s['name']
    if name in DROP:
        continue
    o = osm_matched.get(name)
    g = (gsi_addr.get(name) or {}).get('gsi')
    addr = (gsi_addr.get(name) or {}).get('address', '')
    src, lat, lng = None, None, None
    if name == 'ビバホーム荒巻店':
        ng = new_geo['ビバホーム荒巻店']
        src, lat, lng, addr = 'gsi_addr', ng['lat'], ng['lng'], ng['address']
    elif name == '中山鳥瀧不動尊（目の神様）':
        src, lat, lng = 'osm:exact', 38.2956402, 140.8414793  # 平田稲荷神社と同一境内
        addr = new_geo['中山鳥瀧不動尊（目の神様）']['address']
    elif name in COORD_OVERRIDE:
        src, lat, lng = COORD_OVERRIDE[name]
        if lat is None:
            lat, lng, src = g['lat'], g['lng'], 'gsi_addr'
    elif o:
        src, lat, lng = 'osm:' + o['match'], o['lat'], o['lng']
    elif g:
        src, lat, lng = 'gsi_addr', g['lat'], g['lng']
    if lat is None:
        raise SystemExit('NO COORDS: ' + name)
    disp = RENAME.get(name, name)
    note = s.get('note', '')
    if name == 'なかやまとびのこ公園':
        note = (note + ' ' if note else '') + '「水の神」'
    shops.append({
        'name': disp,
        'cat': RECAT.get(name, s['cat']),
        'url': s['url'], 'voices': s.get('voices', []),
        'note': note, 'addr': ADDR_FIX.get(disp, addr),
        'lat': lat, 'lng': lng, 'src': src,
    })

# 新規10店 + ビバホーム/鳥瀧不動尊のGSI座標
NEW_DISPLAY = {  # 紙マップ表記
    '学習塾 スクールIE 仙台中山校': 'スクールIE 仙台中山校',
}
for a in new_geo.values():
    if a['name'] in ('ビバホーム荒巻店', '中山鳥瀧不動尊（目の神様）'):
        continue  # 既存リスト側で処理済
    if a['name'] == '尚絅教会':
        # OSMノード優先
        shops.append({'name': '尚絅教会', 'cat': 'life', 'url': a['url'], 'voices': [],
                      'note': '', 'addr': a['address'],
                      'lat': 38.2932675, 'lng': 140.8395617, 'src': 'osm:exact'})
        continue
    if a['name'] == 'お菜とお酒アイリス':
        # OSMノード(アイリス restaurant)がGSIと5m一致 → OSM採用
        shops.append({'name': NEW_DISPLAY.get(a['name'], a['name']), 'cat': a['cat'], 'url': a['url'],
                      'voices': [], 'note': '', 'addr': a['address'],
                      'lat': 38.292582, 'lng': 140.841927, 'src': 'osm:exact'})
        continue
    shops.append({'name': NEW_DISPLAY.get(a['name'], a['name']), 'cat': a['cat'], 'url': a['url'],
                  'voices': [], 'note': '', 'addr': a['address'],
                  'lat': a['lat'], 'lng': a['lng'], 'src': a.get('src', 'gsi_addr')})

# 同一住所で個別ピンが確認できなかった組だけ、紙マップの上下順を実座標へ焼き込む。
# 星の描画座標を後段で動かさず、推定点そのものを lat/lng + src=approx として明示する。
def set_approx_pair(upper_name, lower_name):
    upper = next(s for s in shops if s['name'] == upper_name)
    lower = next(s for s in shops if s['name'] == lower_name)
    ux, uy = project(upper['lat'], upper['lng'])
    lx, ly = project(lower['lat'], lower['lng'])
    cx, cy = (ux + lx) / 2, (uy + ly) / 2
    for sh, dx, dy in ((upper, -6.0, -11.0), (lower, 6.0, 11.0)):
        sh['lat'], sh['lng'] = unproject(cx + dx, cy + dy)
        sh['src'] = 'approx'

set_approx_pair('BAKERY&BAKE EndRoll', 'cake NAO')
set_approx_pair('佐藤次夫税理士事務所', 'Double Egg5丁目')
# 振興組合掲載の荒巻本沢1-17-4由来の共通中心へ戻し、紙マップ順で近接2点化。
for _name in ('サトー商会', 'みなとや'):
    _shop = next(s for s in shops if s['name'] == _name)
    _shop['addr'] = '仙台市青葉区荒巻本沢1-17-4'
    _shop['lat'], _shop['lng'] = 38.289295, 140.85054
set_approx_pair('サトー商会', 'みなとや')

# 振興組合掲載の中山5-11-3由来の共通中心へ戻し、紙マップ順ではるの風を上にする。
for _name in ('デイサービス はるの風', '遊季ガーデン'):
    _shop = next(s for s in shops if s['name'] == _name)
    _shop['lat'], _shop['lng'] = 38.292133, 140.842529
set_approx_pair('デイサービス はるの風', '遊季ガーデン')
set_approx_pair('中杜建設', 'ん daccha とこや')

# モニュメント (紙マップ: 坂の登り口・多夢多夢舎の東の道路沿い) — 位置は概算
shops.append({'name': '商店街モニュメント', 'cat': 'place', 'url': '#', 'voices': [],
              'note': '中山の坂の登り口にあるモニュメントが商店街への目印です！',
              'addr': '', 'lat': 38.28810, 'lng': 140.84642, 'src': 'approx'})

# たきみち公園 (紙マップ右下・OSM公園ポリゴン実在) — タップ可能スポットとして追加
shops.append({'name': 'たきみち公園', 'cat': 'place', 'url': '#', 'voices': [],
              'note': '', 'addr': '', 'lat': 38.291917, 'lng': 140.85282, 'src': 'osm:exact'})

# あみさんFBテスト版: 本番生成は変えず、--preview の時だけ写真と坂の上を加える。
PREVIEW_PHOTOS = {
    'なかやまとびのこ公園': [
        {'src': 'assets/photos/tobinoko_1', 'alt': 'なかやまとびのこ公園の東屋とすべり台'},
        {'src': 'assets/photos/tobinoko_2', 'alt': 'なかやまとびのこ公園の石組みの小川'},
    ],
    '中山山の神公園': [
        {'src': 'assets/photos/yamanokami_1', 'alt': '中山山の神公園のブランコとすべり台と芝生'},
        {'src': 'assets/photos/yamanokami_2', 'alt': '中山山の神公園の大きな木と芝生広場'},
    ],
    'たきみち公園': [
        {'src': 'assets/photos/takimichi_1', 'alt': 'たきみち公園の桜とすべり台と石碑'},
        {'src': 'assets/photos/takimichi_2', 'alt': 'たきみち公園の桜の木'},
    ],
}
if ARGS.preview:
    for sh in shops:
        photos = PREVIEW_PHOTOS.get(sh['name'])
        if not photos:
            continue
        # JSON上でもvoicesの直後にphotosを置く。
        ordered = {}
        for key, value in sh.items():
            ordered[key] = value
            if key == 'voices':
                ordered['photos'] = photos
        sh.clear()
        sh.update(ordered)
    shops.append({
        'name': '中山の坂の上', 'cat': 'place', 'url': '#', 'voices': [],
        'photos': [{'src': 'assets/photos/sakanoue_1', 'alt': '中山の坂の上から見た市街地の眺め'}],
        'note': 'バス通りでいちばん高いところ（標高155m）。ここから南へ下る坂が「中山の坂」で、坂の上からは市街地が見渡せます。',
        'addr': '', 'lat': 38.294850, 'lng': 140.836401, 'src': 'gsi_dem',
    })

# ---------------- 道路・河川・公園 ----------------
raw = json.load(open(P('osm_raw2.json'), encoding='utf-8'))
oq3 = json.load(open(P('oq3.json'), encoding='utf-8'))

# 遠隔店 (コア域から0.8km以上): 縁クランプ + 距離表記で扱う
OUTLIERS = {'ダイシン長命ヶ丘店', 'Friend vividhair'}

# 表示範囲: コア店舗の投影bbox + マージン
pts = [project(s['lat'], s['lng']) for s in shops if s['name'] not in OUTLIERS]
xs, ys = [p[0] for p in pts], [p[1] for p in pts]
MARGIN = 110
minx, maxx = min(xs) - MARGIN - 85, max(xs) + MARGIN  # 西は+85(うどう沼を収める)
miny, maxy = min(ys) - MARGIN, max(ys) + MARGIN
W, H = round(maxx - minx), round(maxy - miny)
CLIP_PAD = 115
CLIP_RECT = (minx - CLIP_PAD, miny - CLIP_PAD, maxx + CLIP_PAD, maxy + CLIP_PAD)

def in_view(p, pad=0):
    return (minx - pad) <= p[0] <= (maxx + pad) and (miny - pad) <= p[1] <= (maxy + pad)

def simplify(points, eps=4.0):
    """Douglas-Peucker"""
    if len(points) < 3:
        return points
    def dp(pts_):
        if len(pts_) < 3:
            return pts_
        (x1, y1), (x2, y2) = pts_[0], pts_[-1]
        dmax, idx = 0, 0
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy) or 1e-9
        for i in range(1, len(pts_) - 1):
            d = abs(dy * pts_[i][0] - dx * pts_[i][1] + x2 * y1 - y2 * x1) / norm
            if d > dmax:
                dmax, idx = d, i
        if dmax > eps:
            return dp(pts_[:idx + 1])[:-1] + dp(pts_[idx:])
        return [pts_[0], pts_[-1]]
    return dp(points)

_CS_LEFT, _CS_RIGHT, _CS_TOP, _CS_BOTTOM = 1, 2, 4, 8

def _outcode(p, rect=CLIP_RECT):
    xmin, ymin, xmax, ymax = rect
    code = 0
    if p[0] < xmin: code |= _CS_LEFT
    elif p[0] > xmax: code |= _CS_RIGHT
    if p[1] < ymin: code |= _CS_TOP
    elif p[1] > ymax: code |= _CS_BOTTOM
    return code

def clip_segment(a, b, rect=CLIP_RECT):
    """Cohen–Sutherland。交差点を矩形境界へ正確に置く。"""
    xmin, ymin, xmax, ymax = rect
    x1, y1 = a
    x2, y2 = b
    c1, c2 = _outcode((x1, y1), rect), _outcode((x2, y2), rect)
    while True:
        if not (c1 | c2):
            return (x1, y1), (x2, y2)
        if c1 & c2:
            return None
        code = c1 or c2
        if code & _CS_TOP:
            x = x1 + (x2 - x1) * (ymin - y1) / ((y2 - y1) or 1e-12); y = ymin
        elif code & _CS_BOTTOM:
            x = x1 + (x2 - x1) * (ymax - y1) / ((y2 - y1) or 1e-12); y = ymax
        elif code & _CS_RIGHT:
            y = y1 + (y2 - y1) * (xmax - x1) / ((x2 - x1) or 1e-12); x = xmax
        else:
            y = y1 + (y2 - y1) * (xmin - x1) / ((x2 - x1) or 1e-12); x = xmin
        if code == c1:
            x1, y1, c1 = x, y, _outcode((x, y), rect)
        else:
            x2, y2, c2 = x, y, _outcode((x, y), rect)

def clip_line(points):
    """ポリラインを線分単位で切り、連続する可視線分だけをまとめる。"""
    segs, cur = [], []
    for a, b in zip(points, points[1:]):
        clipped = clip_segment(a, b)
        if clipped is None:
            if len(cur) >= 2: segs.append(cur)
            cur = []
            continue
        ca, cb = clipped
        if not cur or math.hypot(cur[-1][0] - ca[0], cur[-1][1] - ca[1]) > 0.01:
            if len(cur) >= 2: segs.append(cur)
            cur = [ca, cb]
        else:
            cur.append(cb)
    if len(cur) >= 2: segs.append(cur)
    return segs

def on_clip_boundary(p, tolerance=0.05):
    xmin, ymin, xmax, ymax = CLIP_RECT
    return (abs(p[0]-xmin) <= tolerance or abs(p[0]-xmax) <= tolerance or
            abs(p[1]-ymin) <= tolerance or abs(p[1]-ymax) <= tolerance)

# 道路は名称ではなく OSM highway class を正とする。
CLASS_MAP = {
    'primary': 'major', 'secondary': 'major',
    'tertiary': 'mid', 'unclassified': 'mid',
    'residential': 'minor', 'living_street': 'minor',
    'service': 'service',
    'footway': 'path', 'path': 'path', 'steps': 'path',
}
SPINE_ROAD_NAMES = {'中山幹線１号線', '中山幹線1号線'}

def line_length(points):
    return sum(math.hypot(b[0]-a[0], b[1]-a[1]) for a, b in zip(points, points[1:]))

def point_segment_distance(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    den = dx*dx + dy*dy
    if den <= 1e-12: return math.hypot(p[0]-a[0], p[1]-a[1])
    t = max(0.0, min(1.0, ((p[0]-a[0])*dx + (p[1]-a[1])*dy) / den))
    return math.hypot(p[0]-(a[0]+t*dx), p[1]-(a[1]+t*dy))

def point_polyline_distance(p, points):
    return min((point_segment_distance(p, a, b) for a, b in zip(points, points[1:])), default=1e9)

road_fragments = []
for e in raw['elements']:
    t = e.get('tags', {})
    hw = t.get('highway')
    if e.get('type') != 'way' or 'geometry' not in e or hw not in CLASS_MAP:
        continue
    road_name = t.get('name', '')
    cls = 'spine' if road_name in SPINE_ROAD_NAMES else CLASS_MAP[hw]
    source = [project(g['lat'], g['lon']) for g in e['geometry']]
    if len(source) < 2:
        continue
    for seg in clip_line(source):
        if line_length(seg) < 0.5:
            continue
        road_fragments.append({
            'cls': cls, 'name': road_name, 'highways': {hw}, 'raw_ids': {e.get('id')},
            'guide_spine': cls == 'spine', 'pts': seg,
            'start_source': math.hypot(seg[0][0]-source[0][0], seg[0][1]-source[0][1]) < 0.05,
            'end_source': math.hypot(seg[-1][0]-source[-1][0], seg[-1][1]-source[-1][1]) < 0.05,
            'start_boundary': on_clip_boundary(seg[0]), 'end_boundary': on_clip_boundary(seg[-1]),
        })

def endpoint_clusters(items, tolerance=2.0):
    """端点を2m以内で同一ノード化する。内部点は動かさない。"""
    cell = tolerance
    grid, centers, counts = defaultdict(list), [], []
    def locate(p):
        gx, gy = math.floor(p[0]/cell), math.floor(p[1]/cell)
        best, best_d = None, tolerance + 1e-9
        for ix in range(gx-1, gx+2):
            for iy in range(gy-1, gy+2):
                for node in grid[(ix, iy)]:
                    d = math.hypot(p[0]-centers[node][0], p[1]-centers[node][1])
                    if d < best_d: best, best_d = node, d
        if best is not None:
            n = counts[best] + 1
            centers[best] = ((centers[best][0]*counts[best]+p[0])/n,
                             (centers[best][1]*counts[best]+p[1])/n)
            counts[best] = n
            return best
        node = len(centers)
        centers.append(p); counts.append(1); grid[(gx, gy)].append(node)
        return node
    nodes = [(locate(r['pts'][0]), locate(r['pts'][-1])) for r in items]
    return nodes

def merge_chains(items):
    """同classで次数2の端点チェーンを結合。異なる実名同士は結ばない。"""
    merged_all = []
    for cls in ('service', 'minor', 'mid', 'major', 'spine', 'path'):
        group = [r for r in items if r['cls'] == cls]
        if not group: continue
        nodes = endpoint_clusters(group)
        adjacency = defaultdict(list)
        for i, (a, b) in enumerate(nodes):
            adjacency[a].append((i, 0)); adjacency[b].append((i, 1))
        mergeable = {}
        for node, refs in adjacency.items():
            if len(refs) != 2 or refs[0][0] == refs[1][0]:
                mergeable[node] = False
                continue
            n1, n2 = group[refs[0][0]]['name'], group[refs[1][0]]['name']
            mergeable[node] = not n1 or not n2 or n1 == n2
        visited = set()

        def walk(first, start_node):
            idx, node = first, start_node
            out, parts = [], []
            start_source = start_boundary = False
            end_source = end_boundary = False
            while idx not in visited:
                visited.add(idx)
                edge = group[idx]
                side = 0 if nodes[idx][0] == node else 1
                oriented = edge['pts'] if side == 0 else list(reversed(edge['pts']))
                ss = edge['start_source'] if side == 0 else edge['end_source']
                sb = edge['start_boundary'] if side == 0 else edge['end_boundary']
                es = edge['end_source'] if side == 0 else edge['start_source']
                eb = edge['end_boundary'] if side == 0 else edge['start_boundary']
                if not out:
                    out = list(oriented); start_source, start_boundary = ss, sb
                else:
                    joint = ((out[-1][0]+oriented[0][0])/2, (out[-1][1]+oriented[0][1])/2)
                    out[-1] = joint; out.extend(oriented[1:])
                parts.append(edge); end_source, end_boundary = es, eb
                end_node = nodes[idx][1-side]
                if not mergeable.get(end_node, False): break
                candidates = [j for j, _ in adjacency[end_node] if j != idx and j not in visited]
                if len(candidates) != 1: break
                idx, node = candidates[0], end_node
            names = {p['name'] for p in parts if p['name']}
            return {
                'cls': cls, 'name': max(names, key=len) if names else '',
                'highways': set().union(*(p['highways'] for p in parts)),
                'raw_ids': set().union(*(p['raw_ids'] for p in parts)),
                'guide_spine': cls == 'spine', 'pts': out,
                'start_source': start_source, 'end_source': end_source,
                'start_boundary': start_boundary, 'end_boundary': end_boundary,
            }

        for i in range(len(group)):
            if i in visited: continue
            start = next((n for n in nodes[i] if not mergeable.get(n, False)), None)
            if start is not None: merged_all.append(walk(i, start))
        for i in range(len(group)):
            if i not in visited: merged_all.append(walk(i, nodes[i][0]))
    return merged_all

def endpoint_states(items, tolerance=2.0, boundary_check=on_clip_boundary):
    states = []
    for i, road in enumerate(items):
        pair = []
        for p in (road['pts'][0], road['pts'][-1]):
            boundary = boundary_check(p)
            connected = any(
                j != i and point_polyline_distance(p, other['pts']) < tolerance
                for j, other in enumerate(items)
            )
            pair.append({'boundary': boundary, 'connected': connected})
        states.append(pair)
    return states

# 1) 端点チェーン統合 2) 通り抜けでないmidをminorへ 3) 40m未満の孤立片を除去。
roads_stage = merge_chains(road_fragments)
states = endpoint_states(roads_stage)
cleaned, downgraded_mid, removed_isolated = [], 0, 0
for road, ends in zip(roads_stage, states):
    length = line_length(road['pts'])
    touches = [e['boundary'] or e['connected'] for e in ends]
    isolated_short = length < 40 and not any(touches)
    if road['cls'] == 'mid' and not all(touches):
        road['cls'] = 'minor'
        road['guide_spine'] = False
        downgraded_mid += 1
    if isolated_short:
        if road['cls'] in ('major', 'mid', 'spine'):
            road['cls'] = 'minor'
            road['guide_spine'] = False
        else:
            removed_isolated += 1
            continue
    cleaned.append(road)

roads_internal = merge_chains(cleaned)
final_states = endpoint_states(roads_internal)
floating_endpoints = actual_dead_ends = boundary_endpoints = connected_endpoints = 0
for road, ends in zip(roads_internal, final_states):
    source_flags = (road['start_source'], road['end_source'])
    for end, source in zip(ends, source_flags):
        if end['boundary']: boundary_endpoints += 1
        if end['connected']: connected_endpoints += 1
        if not end['boundary'] and not end['connected']:
            if source: actual_dead_ends += 1
            else: floating_endpoints += 1
assert floating_endpoints == 0, 'floating road endpoints: %d' % floating_endpoints

roads = []
for road in roads_internal:
    # 道路の接続点は省略しない。RDPで交差点の内部頂点を落とすと、最終GEOだけ
    # 中空端点が再発するため。class別d連結によりDOM性能は点数に依存しない。
    roads.append({
        'cls': road['cls'], 'name': road['name'], 'guide_spine': road['cls'] == 'spine',
        'pts': [list(p) for p in road['pts']],
        '_start_source': road['start_source'], '_end_source': road['end_source'],
        '_start_boundary': road['start_boundary'], '_end_boundary': road['end_boundary'],
    })
road_counts = dict(sorted(Counter(r['cls'] for r in roads).items()))

rivers = []
for e in raw['elements']:
    t = e.get('tags', {})
    if e['type'] != 'way' or 'geometry' not in e or not t.get('waterway'):
        continue
    if t['waterway'] not in ('river', 'stream'):
        continue
    pts_ = [project(g['lat'], g['lon']) for g in e['geometry']]
    for seg in clip_line(pts_):
        sp = simplify(seg, eps=3.5)
        rivers.append({'name': t.get('name', ''),
                       'pts': [[round(x, 1), round(y, 1)] for x, y in sp]})

PARK_KEEP = {'中山とびのこ公園', '中山山の神公園', 'たきみち公園', 'うどう沼公園'}
parks, waters = [], []
for e in oq3['elements']:
    t = e.get('tags', {})
    if 'geometry' not in e:
        continue
    pts_ = [project(g['lat'], g['lon']) for g in e['geometry']]
    # 閉リング(公園/水域)は簡略化すると小形状が潰れるためそのまま使う
    if t.get('leisure') == 'park' and t.get('name') in PARK_KEEP:
        parks.append({'name': t['name'], 'pts': [[round(x, 1), round(y, 1)] for x, y in pts_]})
    if t.get('natural') == 'water':
        if any(in_view(p, pad=0) for p in pts_):
            waters.append({'name': t.get('name', ''), 'pts': [[round(x, 1), round(y, 1)] for x, y in pts_]})

# 参道 footway (鳥瀧不動尊への道)
sando = []
for e in oq3['elements']:
    t = e.get('tags', {})
    if 'geometry' not in e or t.get('highway') not in ('footway', 'path', 'steps'):
        continue
    pts_ = [project(g['lat'], g['lon']) for g in e['geometry']]
    if any(in_view(p) for p in pts_):
        sando.append([[round(x, 1), round(y, 1)] for x, y in simplify(pts_, 3)])

# バス通り(中山幹線1号線)は、同じ正本道路ジオメトリから導出する。
busway = [[list(p) for p in r['pts']] for r in roads if r['cls'] == 'spine']

# Double Egg 4丁目: 住所が判明したので概算配置を廃止し、COORD_OVERRIDE の実座標を使う。
# 旧実装は「バス通り中心 -75m」の手置き(src=approx)で、実座標から151.2mズレていた。
de4 = next(s for s in shops if s['name'] == 'Double Egg4丁目')
de4['addr'] = de4.get('addr') or '仙台市青葉区中山4-6-36'

# ラベルを星の右/左どちらに置くかだけを指定する。上下・斜めオフセットは禁止。
SHOP_HINTS = {
    '東北電力研究開発センター': {'anchor': 'end'},
    'ヨークベニマル 仙台中山店': {'anchor': 'end'},
    '商店街モニュメント': {'anchor': 'end'},
    'みなみ歯科クリニック': {'anchor': 'start'},
    'カーブス アクロスガーデン中山': {'anchor': 'start'},
    '認定こども園 TOBINOKO': {'anchor': 'end'},
    '多夢多夢舎中山工房': {'anchor': 'end'},
    '中山ドライブスクール': {'anchor': 'end'},
    'サトー商会': {'anchor': 'start'},
}
for sh in shops:
    if sh['name'] in SHOP_HINTS:
        sh['hint'] = SHOP_HINTS[sh['name']]

# ---------------- 投影座標を付与・正規化 ----------------
EDGE = 55  # 縁クランプ位置
for sh in shops:
    x, y = project(sh['lat'], sh['lng'])
    if sh['name'] in OUTLIERS:
        cx, cy = max(minx + EDGE, min(maxx - EDGE, x)), max(miny + EDGE, min(maxy - EDGE, y))
        dist = math.hypot(x - cx, y - cy)
        if dist >= 25:  # 実位置が描画域内(または僅差)ならクランプ扱いにしない
            ang = math.degrees(math.atan2(-(y - cy), x - cx))  # 数学角(deg, 東=0 反時計)
            sh['clamped'] = True
            sh['far_m'] = max(50, int(round(dist / 50.0) * 50))
            sh['far_deg'] = round(ang)
            x, y = cx, cy
    sh['x'], sh['y'] = round(x - minx, 1), round(y - miny, 1)
    if not sh.get('clamped'):
        # 固定星の不変条件。tx/ty は検査用に同値を保持し、表示座標を後処理で動かさない。
        sh['tx'], sh['ty'] = sh['x'], sh['y']

def wobble(x, y, amp=2.3):
    """手描き風の揺らぎをビルド時に焼き込む (SVGフィルタのラスタライズ負荷を回避)"""
    dx = amp * math.sin(y * 0.031 + x * 0.013) + amp * 0.55 * math.sin(y * 0.115)
    dy = amp * math.sin(x * 0.029 + y * 0.017) + amp * 0.55 * math.sin(x * 0.094)
    return x + dx, y + dy

def shift(obj_list, wob=True):
    for o in obj_list:
        pts = [(x - minx, y - miny) for x, y in o['pts']]
        if wob:
            pts = [wobble(x, y) for x, y in pts]
        o['pts'] = [[round(x, 1), round(y, 1)] for x, y in pts]

def shift_roads_topology_safe():
    """共有点へ同じ揺らぎを適用し、クリップ端点だけはSVG外周へ戻す。"""
    xmin, ymin, xmax, ymax = CLIP_RECT
    for road in roads:
        source_pts = road['pts']
        shifted = []
        for x, y in source_pts:
            wx, wy = wobble(x - minx, y - miny)
            # 外周で丸キャップが中途半端に見えないよう、交差した辺へ正確に固定する。
            if abs(x - xmin) <= 0.2: wx = -CLIP_PAD
            elif abs(x - xmax) <= 0.2: wx = W + CLIP_PAD
            if abs(y - ymin) <= 0.2: wy = -CLIP_PAD
            elif abs(y - ymax) <= 0.2: wy = H + CLIP_PAD
            shifted.append([round(wx, 1), round(wy, 1)])
        road['pts'] = shifted

shift_roads_topology_safe()
for coll in (rivers, parks, waters):
    shift(coll)
# AOI帯は最終spineと同一ジオメトリを使い、道路とのずれを作らない。
busway = [[list(p) for p in r['pts']] for r in roads if r['cls'] == 'spine']
sando = [[[round(v, 1) for v in wobble(x - minx, y - miny)] for x, y in seg] for seg in sando]

def on_canvas_boundary(p, tolerance=0.2):
    return (abs(p[0] + CLIP_PAD) <= tolerance or
            abs(p[0] - (W + CLIP_PAD)) <= tolerance or
            abs(p[1] + CLIP_PAD) <= tolerance or
            abs(p[1] - (H + CLIP_PAD)) <= tolerance)

# 丸め・揺らぎ・外周スナップ後の、実際にGEOへ入る座標で再検査する。
final_states = endpoint_states(roads, tolerance=2.0, boundary_check=on_canvas_boundary)
floating_endpoints = actual_dead_ends = boundary_endpoints = connected_endpoints = 0
for road, ends in zip(roads, final_states):
    source_flags = (road['_start_source'], road['_end_source'])
    for end, source in zip(ends, source_flags):
        if end['boundary']: boundary_endpoints += 1
        if end['connected']: connected_endpoints += 1
        if not end['boundary'] and not end['connected']:
            if source: actual_dead_ends += 1
            else: floating_endpoints += 1
assert floating_endpoints == 0, 'final GEO floating road endpoints: %d' % floating_endpoints
road_quality = {
    'floating_endpoints': floating_endpoints, 'actual_dead_ends': actual_dead_ends,
    'boundary_endpoints': boundary_endpoints, 'connected_endpoints': connected_endpoints,
    'two_point_paths': sum(len(r['pts']) == 2 for r in roads),
    'downgraded_mid': downgraded_mid, 'removed_isolated_under_40m': removed_isolated,
}
for road in roads:
    for key in ('_start_source', '_end_source', '_start_boundary', '_end_boundary'):
        road.pop(key)
if ARGS.preview:
    print('roads by class:', road_counts)
    print('road endpoint quality (final GEO):', road_quality)

# 方面表記 (道路の縁到達点から)
def edge_exit(road_name, pick):
    cands = []
    for r in roads:
        if r['name'] != road_name:
            continue
        for p in (r['pts'][0], r['pts'][-1]):
            cands.append(p)
    if not cands:
        return None
    return pick(cands)

exits = []
p = edge_exit('中山幹線２号線', lambda c: min(c, key=lambda q: q[1]))
if p: exits.append({'x': p[0], 'y': max(p[1], -60), 'text': '↑ 至 南中山', 'anchor': 'middle'})
p = edge_exit('荒巻泉線', lambda c: min(c, key=lambda q: q[1]))
if p: exits.append({'x': min(max(p[0], W + 70), W + 100), 'y': p[1] - 12,
                    'text': '至 泉中央 →', 'anchor': 'end'})
p = edge_exit('通町中山線', lambda c: max(c, key=lambda q: q[1]))
if p: exits.append({'x': p[0], 'y': min(p[1] + 28, H + 95), 'text': '↓ 至 北山', 'anchor': 'middle'})
_north0 = project(LAT0, LON0)
_north1 = project(LAT0 + 0.001, LON0)
_north_dx, _north_dy = _north1[0] - _north0[0], _north1[1] - _north0[1]
_north_screen_deg = math.degrees(math.atan2(_north_dx, -_north_dy))
meta = {'W': W, 'H': H, 'proj': unproject_expr(), 'minx': round(minx, 2), 'miny': round(miny, 2),
         'scale_m_per_px': 1.0, 'info_as_of': INFO_AS_OF,
         'road_counts': road_counts, 'road_quality': road_quality,
         'north_vector': [round(_north_dx, 4), round(_north_dy, 4)],
         'north_screen_deg': round(_north_screen_deg, 4),
         'partner_logos': [{
            'name': '宮城大学',
            'src': MIYAGI_UNIVERSITY_LOGO_SRC,
            'alt': '宮城大学',
            'status': 'approved' if MIYAGI_UNIVERSITY_LOGO_SRC else 'permission_pending',
        }]}

# ---------------- 星は実座標へ固定 ----------------
# 密集部でも星・ゾーンは展開しない。可読性はテンプレート側のラベル配置と段階表示で解く。

# タップ領域は隣の星と重ならない半径に (最小12・最大22)
for sh in shops:
    nn = min((math.hypot(sh['x'] - o['x'], sh['y'] - o['y'])
              for o in shops if o is not sh), default=44)
    sh['padr'] = max(12, min(22, int(nn / 2) - 1))

# 指示書で確定済みのDEM地点は、既存店向けの自動スプレッド対象にしない。
# 投影直後の座標へ戻し、指定されたタップ領域もそのまま保持する。
if ARGS.preview:
    slope_top = next(sh for sh in shops if sh['name'] == '中山の坂の上')
    slope_top['x'], slope_top['y'], slope_top['padr'] = 427.8, 270.0, 22
    slope_top['tx'], slope_top['ty'] = slope_top['x'], slope_top['y']

# ---------------- 信号機 (signals_raw.json の canvas 内全ノード) ----------------
signals = []
_sig_raw = json.load(open(P('signals_raw.json'), encoding='utf-8'))
_signal_elements = []
for e in _sig_raw.get('elements', []):
    tags = e.get('tags', {})
    is_signal = tags.get('highway') == 'traffic_signals' or tags.get('crossing') == 'traffic_signals'
    if e.get('lat') is None or not is_signal:
        continue
    sx, sy = project(e['lat'], e['lon'])
    sx, sy = sx - minx, sy - miny
    if 0 <= sx <= W and 0 <= sy <= H:
        _signal_elements.append((e.get('id', 0), sx, sy))
for _, sx, sy in sorted(_signal_elements):
    signals.append([round(sx, 1), round(sy, 1)])
meta['signal_counts'] = {'raw_canvas': len(_signal_elements), 'displayed': len(signals)}
assert meta['signal_counts']['raw_canvas'] == meta['signal_counts']['displayed']
if ARGS.preview:
    print('signals raw canvas/displayed:', len(_signal_elements), '/', len(signals))

# 旧来の密集ゾーン展開は廃止。星は固定し、ラベルだけをブラウザ側で整理する。
zones = []

if not ARGS.preview:
    # Task H: 本番は既存mapdataの店舗・地物を正本にし、表示座標だけを真座標へ戻す。
    # tx/tyが無い店は既存x/yが真座標。EndRoll/cake NAOだけ確定済みの上下へ正規化する。
    generated_names = {sh['name'] for sh in shops}
    baseline_names = {sh['name'] for sh in PRODUCTION_BASELINE['shops']}
    if generated_names != baseline_names:
        raise SystemExit('production shop guard failed: generated/baseline names differ')
    shops = json.loads(json.dumps(PRODUCTION_BASELINE['shops'], ensure_ascii=False))
    for sh in shops:
        sh['x'] = sh.get('tx', sh['x'])
        sh['y'] = sh.get('ty', sh['y'])

    # Double Egg 4丁目: 凍結ベースの座標は手置きの概算(src=approx / バス通り中心-75m)。
    # 住所が判明したので実測座標へ差し替える。
    #   住所 = 仙台市青葉区中山4丁目6-36 (イートイン専門店。5丁目19-5 はテイクアウト専門の別店舗)
    #   出典 = 公式 w-egg.jp / Yahoo!マップ「オムライス食堂 Double Egg 4丁目店」
    #   国土地理院 住所検索APIで号レベル一致「宮城県仙台市青葉区中山四丁目６番３６号」
    # 凍結ベースのx/yは投影後にオフセット済みなので、既知店から同じオフセットを逆算して合わせる。
    DE4_FIX = {'addr': '仙台市青葉区中山4-6-36', 'lat': 38.291851, 'lng': 140.842712}
    _ref = next(sh for sh in shops if sh['name'] == '柏屋')          # osm:exact・微小変位の対象外
    _rx, _ry = project(_ref['lat'], _ref['lng'])
    _ox, _oy = _ref.get('tx', _ref['x']) - _rx, _ref.get('ty', _ref['y']) - _ry
    _de4 = next(sh for sh in shops if sh['name'] == 'Double Egg4丁目')
    _nx, _ny = project(DE4_FIX['lat'], DE4_FIX['lng'])
    _nx, _ny = round(_nx + _ox, 1), round(_ny + _oy, 1)
    # mapdata.json は毎ビルドで上書きされる = 2回目以降のベースは既に修正済み。冪等にする。
    _moved = math.hypot(_nx - _de4['x'], _ny - _de4['y'])
    if not (0 <= _nx <= W and 0 <= _ny <= H):
        raise SystemExit('Double Egg4丁目 fix guard: canvas外 xy=(%.1f,%.1f)' % (_nx, _ny))
    _de4.update({'addr': DE4_FIX['addr'], 'lat': DE4_FIX['lat'], 'lng': DE4_FIX['lng'],
                 'src': 'gsi_addr', 'x': _nx, 'y': _ny, 'tx': _nx, 'ty': _ny})
    print('Double Egg4丁目: 住所由来座標 xy=(%.1f,%.1f) (ベースからの移動 %.1fm)' % (_nx, _ny, _moved))

    endroll = next(sh for sh in shops if sh['name'] == 'BAKERY&BAKE EndRoll')
    cake_nao = next(sh for sh in shops if sh['name'] == 'cake NAO')
    pair_positions = sorted(
        [(sh.get('tx', sh['x']), sh.get('ty', sh['y'])) for sh in (endroll, cake_nao)],
        key=lambda p: (p[1], p[0]),
    )
    for sh, (px, py) in ((endroll, pair_positions[0]), (cake_nao, pair_positions[1])):
        sh['x'], sh['y'], sh['tx'], sh['ty'] = px, py, px, py

    same_address_pairs = [
        ('BAKERY&BAKE EndRoll', 'cake NAO'),
        ('佐藤次夫税理士事務所', 'Double Egg5丁目'),
        ('サトー商会', 'みなとや'),
        ('デイサービス はるの風', '遊季ガーデン'),
        ('中杜建設', 'ん daccha とこや'),
    ]
    by_name = {sh['name']: sh for sh in shops}
    for upper_name, lower_name in same_address_pairs:
        upper, lower = by_name[upper_name], by_name[lower_name]
        separation = math.hypot(lower['x'] - upper['x'], lower['y'] - upper['y'])
        if not upper['y'] < lower['y'] or not 13.8 <= separation <= 14.2:
            raise SystemExit('same-address pair guard failed: %s / %s' % (upper_name, lower_name))

    # Task Hで許可された8m以内の微小変位。tx/tyは真座標のまま保持し、
    # 15m未満の密集点だけを東西・南北順を壊さずに離す。
    marker_offsets = {
        'BURB usedclothing': (0.0, -0.3),
        'レストラン KAYA': (0.0, 0.3),
        'おたからや': (-8.0, 0.0),
        '佐藤次夫税理士事務所': (7.0, -0.6),
        'Double Egg5丁目': (0.0, 0.6),
        '中山不動産': (8.0, 0.0),
        '中杜建設': (-4.0, -0.6),
        '花祭壇': (-8.0, 0.0),
        'ん daccha とこや': (-5.0, 0.6),
        'ダイニングバー 祭': (8.0, 0.0),
        '中山鍼灸接骨院': (0.0, -0.8),
        'フラワー中山': (0.0, 0.8),
        'カットショップ NOBU': (0.0, -0.5),
        '梅原表具店': (0.0, 0.5),
        'BAKERY&BAKE EndRoll': (0.0, -0.6),
        'cake NAO': (0.0, 0.6),
        '認定こども園 TOBINOKO': (3.0, 0.0),
        '商店街モニュメント': (-3.0, 0.0),
        'サトー商会': (0.0, -0.6),
        'みなとや': (0.0, 0.6),
        'デイサービス はるの風': (0.0, -0.6),
        '遊季ガーデン': (0.0, 0.6),
    }
    true_positions = {sh['name']: (sh['x'], sh['y']) for sh in shops}
    for name, (dx, dy) in marker_offsets.items():
        sh = by_name[name]
        if math.hypot(dx, dy) > 8.0 + 1e-9:
            raise SystemExit('marker offset exceeds 8m: %s' % name)
        sh['x'], sh['y'] = round(sh['x'] + dx, 1), round(sh['y'] + dy, 1)

    def production_bus_x_at(y):
        points = PRODUCTION_BASELINE['busway'][1]
        nearest = None
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            lo, hi = min(y1, y2), max(y1, y2)
            if lo <= y <= hi:
                t = 0.0 if y2 == y1 else (y - y1) / (y2 - y1)
                return x1 + t * (x2 - x1)
            for x, py in ((x1, y1), (x2, y2)):
                candidate = (abs(y - py), x)
                if nearest is None or candidate < nearest:
                    nearest = candidate
        return nearest[1]

    for i, sh in enumerate(shops):
        tx, ty = true_positions[sh['name']]
        if ((tx >= production_bus_x_at(ty)) !=
                (sh['x'] >= production_bus_x_at(sh['y']))):
            raise SystemExit('marker offset crossed busway: %s' % sh['name'])
        for other in shops[i + 1:]:
            otx, oty = true_positions[other['name']]
            if (ty - oty) * (sh['y'] - other['y']) < 0:
                raise SystemExit('marker offset inverted north/south order: %s / %s' %
                                 (sh['name'], other['name']))
            if math.hypot(sh['x'] - other['x'], sh['y'] - other['y']) < 15.0:
                raise SystemExit('marker offset left a pair under 15m: %s / %s' %
                                 (sh['name'], other['name']))

    # 店舗以外の本番地物はbyte由来の凍結データを維持する。
    meta = json.loads(json.dumps(PRODUCTION_BASELINE['meta'], ensure_ascii=False))
    roads = json.loads(json.dumps(PRODUCTION_BASELINE['roads'], ensure_ascii=False))
    rivers = json.loads(json.dumps(PRODUCTION_BASELINE['rivers'], ensure_ascii=False))
    parks = json.loads(json.dumps(PRODUCTION_BASELINE['parks'], ensure_ascii=False))
    waters = json.loads(json.dumps(PRODUCTION_BASELINE['waters'], ensure_ascii=False))
    sando = json.loads(json.dumps(PRODUCTION_BASELINE['sando'], ensure_ascii=False))
    busway = json.loads(json.dumps(PRODUCTION_BASELINE['busway'], ensure_ascii=False))
    exits = json.loads(json.dumps(PRODUCTION_BASELINE['exits'], ensure_ascii=False))
    signals = json.loads(json.dumps(PRODUCTION_BASELINE['signals'], ensure_ascii=False))
    if len(shops) != 60 or len(roads) != 62 or len(signals) != 13:
        raise SystemExit('production output guard failed: expected shops=60 roads=62 signals=13')
    print('production frozen geometry: shops=60 roads=62 signals=13')

print('zones:', zones)

data = {'meta': meta, 'shops': shops, 'roads': roads, 'rivers': rivers,
        'parks': parks, 'waters': waters, 'sando': sando, 'busway': busway, 'exits': exits,
        'zones': zones, 'signals': signals}
serialized = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
if not ARGS.preview:
    with open(P('mapdata.json'), 'w', encoding='utf-8') as f:
        f.write(serialized)

# ---------------- HTML生成 (テンプレート注入・script破り対策の"</"エスケープ込み) ----------------
with open(TEMPLATE_HTML, encoding='utf-8') as f:
    tpl = f.read()
blob = serialized.replace('</', '<\\/')
rendered = tpl.replace('__MAPDATA_JSON__', blob)
for out_html in OUT_HTMLS:
    with open(out_html, 'w', encoding='utf-8') as f:
        f.write(rendered)
    print('HTML generated (escaped):', out_html)

if ARGS.preview:
    for i, sh in enumerate(shops):
        if sh.get('photos'):
            print('preview photo shop: index=%d name=%s photos=%d' % (i, sh['name'], len(sh['photos'])))

print('shops:', len(shops), ' roads:', len(roads), ' rivers:', len(rivers),
      ' parks:', len(parks), ' waters:', len(waters), ' sando:', len(sando))
print('canvas: %dx%d (1px=1m)' % (W, H))
# 向きの検証: ベニマルが左上・ドライブスクールが右下側にあること
bn = next(s for s in shops if 'ベニマル' in s['name'])
ds = next(s for s in shops if 'ドライブスクール' in s['name'])
po = next(s for s in shops if '郵便局' in s['name'])
print('benimaru xy=(%d,%d)  driveschool xy=(%d,%d)  post=(%d,%d)' % (bn['x'], bn['y'], ds['x'], ds['y'], po['x'], po['y']))
assert bn['y'] < ds['y'], 'orientation broken: benimaru should be above driveschool'
sizes = len(json.dumps(data, ensure_ascii=False))
print('mapdata bytes:', sizes)
