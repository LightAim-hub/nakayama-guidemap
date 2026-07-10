# -*- coding: utf-8 -*-
"""なかやま商店街マップ v2 — 実座標データセット生成 + HTML生成
入力 (スクリプトと同じフォルダ): osm_raw2.json / oq3.json / verified_shops.json /
      shops_geo_osm.json / store_addresses_geo.json / new_shops_geo.json / template.html
出力: mapdata.json (中間) と リポジトリ直下の index.html / v2.html
実行: python tools/v2-build/build_mapdata.py (どこから実行してもよい)
"""
import json, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
def P(name):
    return os.path.join(HERE, name)
# リポジトリ直下 (tools/v2-build/ の2つ上)。無ければスクリプト隣に確認用HTMLを出力
_repo = os.path.abspath(os.path.join(HERE, '..', '..'))
if os.path.isdir(os.path.join(_repo, '.git')):
    OUT_HTMLS = [os.path.join(_repo, 'index.html'), os.path.join(_repo, 'v2.html')]
else:
    OUT_HTMLS = [P('v2_index.html')]

LAT0, LON0 = 38.2935, 140.8435
COSF = math.cos(math.radians(LAT0))
ROT = math.radians(46.4)  # バス通り(方位133.6°)を画面下向きにする時計回り回転
INFO_AS_OF = '2026年6月12日'  # 振興組合支給マップの明記日 (2026-07-10受領)

# 校章等の使用許可と正式画像の受領後にだけパスを設定する。
# 空文字の間はテンプレート側の協力ロゴ欄を表示しない。
MIYAGI_UNIVERSITY_LOGO_SRC = ''

def to_m(lat, lng):
    return ((lng - LON0) * 111320 * COSF, (lat - LAT0) * 111320)

def project(lat, lng):
    mx, my = to_m(lat, lng)
    # 画面: x右 y下。北上向き→x=mx, y=-my。さらに回転ROT(時計回り)
    x0, y0 = mx, -my
    x = x0 * math.cos(ROT) - y0 * math.sin(ROT)
    y = x0 * math.sin(ROT) + y0 * math.cos(ROT)
    return (x, y)

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
    # Double Egg: OSMノード(西側)=4丁目店 / 5丁目店は住所5-19-5(東側)
    'Double Egg 4丁目': ('osm:exact', 38.292811, 140.841566),
    'Double Egg 5丁目': ('gsi_addr', None, None),  # None→GSI値を使う
    '志摩整骨院': ('gsi_addr', None, None),        # OSM同名ノードは西側で紙と不整合
    '中山鳥瀧不動尊（目の神様）': ('osm:exact', 38.2956402, 140.8414793),  # 平田稲荷神社と同一境内
    # みなとや: OSM同名ノードは250m東の別施設疑い。公式住所1-17-4(GSI号レベル解決)を採用
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
                  'lat': a['lat'], 'lng': a['lng'], 'src': 'gsi_addr'})

# 同一住所ビルの店の「表示位置」だけ少しずらす (lat/lngの実座標は汚染しない・Codex R2指摘)
from collections import defaultdict
by_pos = defaultdict(list)
for sh in shops:
    by_pos[(round(sh['lat'], 5), round(sh['lng'], 5))].append(sh)
for pos, group in by_pos.items():
    if len(group) > 1:
        # 縦(通り沿い)方向のみに分散 — 横に散らすと通りの反対側へ渡ってラベル列が壊れる
        for i, sh in enumerate(group):
            sh['disp_dx'] = 0.0
            sh['disp_dy'] = round((i - (len(group) - 1) / 2.0) * 14.0, 1)

# モニュメント (紙マップ: 坂の登り口・多夢多夢舎の東の道路沿い) — 位置は概算
shops.append({'name': '商店街モニュメント', 'cat': 'place', 'url': '#', 'voices': [],
              'note': '中山の坂の登り口にあるモニュメントが商店街への目印です！',
              'addr': '', 'lat': 38.28810, 'lng': 140.84642, 'src': 'approx'})

# たきみち公園 (紙マップ右下・OSM公園ポリゴン実在) — タップ可能スポットとして追加
shops.append({'name': 'たきみち公園', 'cat': 'place', 'url': '#', 'voices': [],
              'note': '', 'addr': '', 'lat': 38.291917, 'lng': 140.85282, 'src': 'osm:exact'})

# ---------------- 道路・河川・公園 ----------------
raw = json.load(open(P('osm_raw2.json'), encoding='utf-8'))
oq3 = json.load(open(P('oq3.json'), encoding='utf-8'))

# 遠隔店 (コア域から0.8km以上): 縁クランプ + 距離表記で扱う
OUTLIERS = {'ダイシン長命ヶ丘店', 'Friend vividhair', 'みなとや', 'サトー商会'}

# 表示範囲: コア店舗の投影bbox + マージン
pts = [project(s['lat'], s['lng']) for s in shops if s['name'] not in OUTLIERS]
xs, ys = [p[0] for p in pts], [p[1] for p in pts]
MARGIN = 110
minx, maxx = min(xs) - MARGIN - 85, max(xs) + MARGIN  # 西は+85(うどう沼を収める)
miny, maxy = min(ys) - MARGIN, max(ys) + MARGIN

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

def clip_line(points):
    """ビュー外区間を落とす(単純: 全点外なら捨て、跨ぎはそのまま残す)"""
    segs, cur = [], []
    for i, p in enumerate(points):
        if in_view(p, pad=60):
            cur.append(p)
        else:
            if cur:
                cur.append(p)  # 縁まで伸ばす
                segs.append(cur)
                cur = []
    if cur:
        segs.append(cur)
    return [s for s in segs if len(s) >= 2]

# 支給マップと同じ目印になる接続路だけを残す。住宅路の全表示は視覚ノイズになるため行わない。
# OSM way id は2026-07-10受領図の交差位置を、店舗の実測座標と照合して固定したもの。
REFERENCE_SIDE_STREET_WAY_IDS = {
    104236630, 998965378,                    # 北側の導入路
    104542851, 104236575,                   # 7丁目・6丁目境
    104236593, 104236598,                   # 中山中学校・鳥瀧不動尊側
    103842633, 103846535,                   # 4丁目・5丁目北側
    103842635, 103846544,                   # 4丁目・5丁目中央
    103842207, 104236852,                   # 2丁目・5丁目南側
    103842201, 104236843,                   # とびのこ公園・小学校側
    103842204, 104236847,                   # 坂の登り口側
}
CLASS_MAP = {'primary': 'major', 'secondary': 'major', 'tertiary': 'mid',
             'unclassified': 'mid', 'residential': 'minor', 'living_street': 'minor'}
BUS_NAMES = ('中山幹線１号線', '中山幹線２号線', '中山幹線1号線', '中山幹線2号線')
CORE_BUS_NAMES = {'中山幹線１号線', '中山幹線1号線'}
SOUTH_BRANCH_NAMES = {'中山幹線２号線', '中山幹線2号線'}
GUIDE_SPINE_NAMES = CORE_BUS_NAMES
GUIDE_SPINE_WAY_IDS = {1017367080}  # ヨークベニマル付近の信号から中央幹線まで
roads = []
for e in raw['elements']:
    t = e.get('tags', {})
    hw = t.get('highway')
    if e['type'] != 'way' or 'geometry' not in e or hw not in CLASS_MAP:
        continue
    if CLASS_MAP[hw] == 'minor' and e.get('id') not in REFERENCE_SIDE_STREET_WAY_IDS:
        continue
    cls = CLASS_MAP[hw]
    road_name = t.get('name', '')
    if road_name in CORE_BUS_NAMES:
        cls = 'major'  # バス通りは商店街の主役なので強調
    elif road_name in SOUTH_BRANCH_NAMES:
        cls = 'mid'  # 南中山方向はT字の太線対象外
    pts_ = [project(g['lat'], g['lon']) for g in e['geometry']]
    for seg in clip_line(pts_):
        sp = simplify(seg, eps=3.5)
        roads.append({'cls': cls, 'name': road_name,
                      'guide_spine': road_name in GUIDE_SPINE_NAMES or e.get('id') in GUIDE_SPINE_WAY_IDS,
                      'pts': [[round(x, 1), round(y, 1)] for x, y in sp]})

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

# バス通り(中山幹線1号線)の全体ポリライン (ラベル配置の基準線)
busway = []
for e in raw['elements']:
    if e['type'] == 'way' and e.get('tags', {}).get('name') in ('中山幹線１号線', '中山幹線2号線', '中山幹線２号線') and 'geometry' in e:
        busway.append([[round(x, 1), round(y, 1)] for x, y in
                       [project(g['lat'], g['lon']) for g in e['geometry']]])

# Double Egg 4丁目: OSMノードは5丁目と同一地点だったため、通りの対面(西側)へ概算配置
# (紙マップでは4丁目店は通りの西側。住所非公開のため要現地確認)
_bus_all = []
for seg in busway:
    _bus_all += seg
def _bus_x_at_y(y):
    pts_s = sorted(_bus_all, key=lambda p: p[1])
    if y <= pts_s[0][1]: return pts_s[0][0]
    if y >= pts_s[-1][1]: return pts_s[-1][0]
    for i in range(1, len(pts_s)):
        if pts_s[i][1] >= y:
            lo, hi = pts_s[i-1], pts_s[i]
            t = (y - lo[1]) / ((hi[1] - lo[1]) or 1e-9)
            return lo[0] + t * (hi[0] - lo[0])
    return pts_s[-1][0]

de4 = next(s for s in shops if s['name'] == 'Double Egg4丁目')
de5 = next(s for s in shops if s['name'] == 'Double Egg5丁目')
_x5, _y5 = project(de5['lat'], de5['lng'])
_bx = _bus_x_at_y(_y5)
# 紙マップでは4丁目店は通りの明確に西側(柏屋・たけむらやの並び)に描かれている
_x4, _y4 = _bx - 75, _y5 + 8
# 逆変換してlat/lngも更新
_rot = -ROT
_gx, _gy = _x4, _y4
_x0 = _gx * math.cos(_rot) - _gy * math.sin(_rot)
_y0 = _gx * math.sin(_rot) + _gy * math.cos(_rot)
de4['lng'] = LON0 + _x0 / (111320 * COSF)
de4['lat'] = LAT0 + (-_y0) / 111320
de4['src'] = 'approx'

# ラベル配置の個別ヒント (テンプレ側で解釈)
SHOP_HINTS = {
    '東北電力研究開発センター': {'anchor': 'middle', 'dy': 27},
    'ヨークベニマル 仙台中山店': {'anchor': 'end', 'dx': -15},
    '商店街モニュメント': {'anchor': 'end', 'dx': -30, 'dy': -4},  # 右端が横断道路帯に触れるため左へ
    'みなみ歯科クリニック': {'anchor': 'end', 'dx': -15, 'dy': 0},  # 右側は上下2本の道路に挟まれ幅不足
    'カーブス アクロスガーデン中山': {'anchor': 'start', 'dx': 15, 'dy': 12},  # 道路間の空きレーンへ
    '認定こども園 TOBINOKO': {'anchor': 'end', 'dx': -15, 'dy': 18},  # 右側はNOBU列と衝突するため左に出す
    '多夢多夢舎中山工房': {'anchor': 'end', 'dx': -15, 'dy': 10},
    '中山ドライブスクール': {'anchor': 'start', 'dx': 15, 'dy': -14},
}
for sh in shops:
    if sh['name'] in SHOP_HINTS:
        sh['hint'] = SHOP_HINTS[sh['name']]

# ---------------- 投影座標を付与・正規化 ----------------
EDGE = 55  # 縁クランプ位置
for sh in shops:
    x, y = project(sh['lat'], sh['lng'])
    x += sh.pop('disp_dx', 0.0)
    y += sh.pop('disp_dy', 0.0)
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
for coll in (roads, rivers, parks, waters):
    shift(coll)
busway = [[[round(x - minx, 1), round(y - miny, 1)] for x, y in seg] for seg in busway]
sando = [[[round(v, 1) for v in wobble(x - minx, y - miny)] for x, y in seg] for seg in sando]

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

W, H = round(maxx - minx), round(maxy - miny)

exits = []
p = edge_exit('中山幹線２号線', lambda c: min(c, key=lambda q: q[1]))
if p: exits.append({'x': p[0], 'y': max(p[1], -60), 'text': '↑ 至 南中山', 'anchor': 'middle'})
p = edge_exit('荒巻泉線', lambda c: min(c, key=lambda q: q[1]))
if p: exits.append({'x': min(max(p[0], W + 70), W + 100), 'y': p[1] - 12,
                    'text': '至 泉中央 →', 'anchor': 'end'})
p = edge_exit('通町中山線', lambda c: max(c, key=lambda q: q[1]))
if p: exits.append({'x': p[0], 'y': min(p[1] + 28, H + 95), 'text': '↓ 至 北山', 'anchor': 'middle'})
meta = {'W': W, 'H': H, 'proj': unproject_expr(), 'minx': round(minx, 2), 'miny': round(miny, 2),
        'scale_m_per_px': 1.0, 'info_as_of': INFO_AS_OF,
        'partner_logos': [{
            'name': '宮城大学',
            'src': MIYAGI_UNIVERSITY_LOGO_SRC,
            'alt': '宮城大学',
            'status': 'approved' if MIYAGI_UNIVERSITY_LOGO_SRC else 'permission_pending',
        }]}

# ---------------- 密集部の星間隔スプレッド ----------------
# 位置関係(並び順・通りの側)は不変のまま、通り沿い方向に最小26px間隔を確保する。
# 真の座標は lat/lng に保持。表示をずらした星は tx/ty に真の表示位置を記録 (?debug=1で可視)。
_bus_shifted = sorted((p for seg in busway for p in seg), key=lambda p: p[1])
def _busx(y):
    if not _bus_shifted:
        return W / 2
    if y <= _bus_shifted[0][1]:
        return _bus_shifted[0][0]
    if y >= _bus_shifted[-1][1]:
        return _bus_shifted[-1][0]
    for k in range(1, len(_bus_shifted)):
        if _bus_shifted[k][1] >= y:
            lo, hi = _bus_shifted[k - 1], _bus_shifted[k]
            t = (y - lo[1]) / ((hi[1] - lo[1]) or 1e-9)
            return lo[0] + t * (hi[0] - lo[0])
    return _bus_shifted[-1][0]

MINGAP_STAR = 40  # 密集店舗の余白 (ボスFB段階拡大: 26→33→40)
# 帯幅160px: 通り近傍の店(ドライブスクール等)も同じ順序保存スプレッドに含め、
# 列だけ動いて近傍店と表示順が逆転する事故を防ぐ
for _side in (-1, 1):
    col = [sh for sh in shops
           if not sh.get('clamped')
           and 240 < sh['y'] < 1560
           and abs(sh['x'] - _busx(sh['y'])) < 160
           and ((sh['x'] - _busx(sh['y'])) <= 0) == (_side < 0)]
    col.sort(key=lambda s: s['y'])
    ys = [s['y'] for s in col]
    for i in range(1, len(ys)):
        if ys[i] < ys[i - 1] + MINGAP_STAR:
            ys[i] = ys[i - 1] + MINGAP_STAR
    for i in range(len(ys) - 2, -1, -1):
        if ys[i] > ys[i + 1] - MINGAP_STAR:
            ys[i] = ys[i + 1] - MINGAP_STAR
    for _ in range(4):
        for i in range(len(ys)):
            lo = ys[i - 1] + MINGAP_STAR if i else -1e9
            hi = ys[i + 1] - MINGAP_STAR if i < len(ys) - 1 else 1e9
            ys[i] = max(lo, min(hi, col[i]['y']))
    for s_, ny in zip(col, ys):
        if abs(ny - s_['y']) > 2:
            s_['tx'], s_['ty'] = s_['x'], s_['y']       # 真の表示位置を保持
            s_['x'] = round(s_['x'] + (_busx(ny) - _busx(s_['y'])), 1)  # 通りのカーブに追従
            s_['y'] = round(ny, 1)

# 道路拡幅に伴う横方向クリアランス: 通り沿いの星は中心線から最低28px離す
# (道路を挟んで向かい合う店の間に「道路の余白」を作る・ボスFB 2026-07-04)
MINOFF_STAR = 42  # 主要道路38px幅(半径19)+星半径10+余白
for sh in shops:
    if sh.get('clamped') or not (240 < sh['y'] < 1460):
        continue
    bx0 = _busx(sh['y'])
    dx0 = sh['x'] - bx0
    if abs(dx0) < 95 and abs(dx0) < MINOFF_STAR:
        if 'tx' not in sh:
            sh['tx'], sh['ty'] = sh['x'], sh['y']
        side_ = -1 if dx0 <= 0 else 1
        sh['x'] = round(bx0 + side_ * MINOFF_STAR, 1)

# 全道路クリアランス: 路面店の星が「どの道路とも」被らない位置へ押し出す
# (OSM座標は店頭=道路縁に載りがち・ボスFB 2026-07-04)
ROAD_HALF = {'major': 19.0, 'mid': 10.5, 'minor': 4.5}
CLEAR_NEED = 14.0  # 星半径10 + 余白4

def _road_half(r):
    if r.get('guide_spine'):
        return 24.0
    return ROAD_HALF[r['cls']]

def _clear_roads_once():
    changed = 0
    for sh in shops:
        if sh.get('clamped'):
            continue
        for r in roads:
            need = _road_half(r) + CLEAR_NEED
            pts_ = r['pts']
            for k in range(1, len(pts_)):
                ax, ay = pts_[k - 1]
                bx2, by2 = pts_[k]
                vx, vy = bx2 - ax, by2 - ay
                L2 = vx * vx + vy * vy
                if L2 < 1e-9:
                    continue
                t = max(0.0, min(1.0, ((sh['x'] - ax) * vx + (sh['y'] - ay) * vy) / L2))
                cx, cy = ax + t * vx, ay + t * vy
                dx, dy = sh['x'] - cx, sh['y'] - cy
                d = math.hypot(dx, dy)
                if d >= need:
                    continue
                if d < 1e-6:  # 道路の真上: 法線方向へ
                    nl = math.hypot(vx, vy)
                    dx, dy, d = -vy / nl, vx / nl, 1.0
                if 'tx' not in sh:
                    sh['tx'], sh['ty'] = sh['x'], sh['y']
                sh['x'] = round(cx + dx / d * need, 1)
                sh['y'] = round(cy + dy / d * need, 1)
                changed += 1
    return changed

for _it in range(4):
    if _clear_roads_once() == 0:
        break

# タップ領域は隣の星と重ならない半径に (最小12・最大22)
for sh in shops:
    nn = min((math.hypot(sh['x'] - o['x'], sh['y'] - o['y'])
              for o in shops if o is not sh), default=44)
    sh['padr'] = max(12, min(22, int(nn / 2) - 1))

# ---------------- 信号機 (OSM実データ + 支給マップFB) ----------------
signals = []
try:
    _sig_raw = json.load(open(P('signals_raw.json'), encoding='utf-8'))
    _sig_pts = []
    for e in _sig_raw.get('elements', []):
        if e.get('lat') is None:
            continue
        sx, sy = project(e['lat'], e['lon'])
        sx, sy = sx - minx, sy - miny
        if -40 <= sx <= W + 40 and -40 <= sy <= H + 40:
            _sig_pts.append((sx, sy))
    for sx, sy in _sig_pts:  # 同一交差点の複数灯を1つに統合
        if all(math.hypot(sx - gx, sy - gy) >= 30 for gx, gy in signals):
            signals.append((round(sx, 1), round(sy, 1)))
    signals = [list(p) for p in signals]
except FileNotFoundError:
    pass

# 2026-07-10 振興組合FB: 位置把握用に3箇所を補足する。
# OSMノード由来ではないため、施設の表示位置と道路中心から毎回再計算する。
_signal_landmarks = [
    ('東北電力研究開発センター', 'below'),
    ('ウジエスーパー中山店', 'bus_side'),
    ('お菜とお酒アイリス', 'bus_side'),
]
for _name, _mode in _signal_landmarks:
    _shop = next(s for s in shops if s['name'] == _name)
    if _mode == 'below':
        # 支給図で施設直下にある交差路へ合わせる。
        _sx, _sy = _shop['x'] + 6, _shop['y'] + 57
    else:
        _sx, _sy = _busx(_shop['y']), _shop['y']
    if all(math.hypot(_sx - gx, _sy - gy) >= 30 for gx, gy in signals):
        signals.append([round(_sx, 1), round(_sy, 1)])
print('signals:', len(signals))

# ---------------- 密集区画の自動検出 (チェーン距離36px・5店以上 → タップで区画一覧) ----------------
_parent = list(range(len(shops)))
def _find(a):
    while _parent[a] != a:
        _parent[a] = _parent[_parent[a]]
        a = _parent[a]
    return a
def _true_xy(sh):
    return (sh.get('tx', sh['x']), sh.get('ty', sh['y']))  # 区画判定はスプレッド前の真の密集で
for _i in range(len(shops)):
    for _j in range(_i + 1, len(shops)):
        if shops[_i].get('clamped') or shops[_j].get('clamped'):
            continue
        ax, ay = _true_xy(shops[_i])
        bx_, by_ = _true_xy(shops[_j])
        if math.hypot(ax - bx_, ay - by_) < 36:
            ra, rb = _find(_i), _find(_j)
            if ra != rb:
                _parent[ra] = rb
_groups = defaultdict(list)
for _i in range(len(shops)):
    _groups[_find(_i)].append(_i)
zones = []
for _members in _groups.values():
    if len(_members) < 5:
        continue
    xs_ = [shops[i]['x'] for i in _members]   # 枠は表示座標で描く
    ys_ = [shops[i]['y'] for i in _members]
    gaps_ = sorted(min(math.hypot(shops[i]['x'] - shops[j]['x'], shops[i]['y'] - shops[j]['y'])
                       for j in _members if j != i) for i in _members)  # ズーム判定も表示座標で
    names_ = {shops[i]['name'] for i in _members}
    zname = '5丁目19番かいわい' if 'ダイニングバー 祭' in names_ else 'この区画'
    zones.append({'name': zname, 'members': sorted(_members, key=lambda i: shops[i]['y']),
                  'x0': round(min(xs_) - 16), 'y0': round(min(ys_) - 16),
                  'x1': round(max(xs_) + 16), 'y1': round(max(ys_) + 16),
                  'gap': round(gaps_[len(gaps_) // 2], 1)})
print('zones:', [(len(z['members']), z['gap']) for z in zones])

data = {'meta': meta, 'shops': shops, 'roads': roads, 'rivers': rivers,
        'parks': parks, 'waters': waters, 'sando': sando, 'busway': busway, 'exits': exits,
        'zones': zones, 'signals': signals}
with open(P('mapdata.json'), 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, separators=(',', ':'))

# ---------------- HTML生成 (テンプレート注入・script破り対策の"</"エスケープ込み) ----------------
with open(P('template.html'), encoding='utf-8') as f:
    tpl = f.read()
with open(P('mapdata.json'), encoding='utf-8') as f:
    blob = f.read().replace('</', '<\\/')
rendered = tpl.replace('__MAPDATA_JSON__', blob)
for out_html in OUT_HTMLS:
    with open(out_html, 'w', encoding='utf-8') as f:
        f.write(rendered)
    print('HTML generated (escaped):', out_html)

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
