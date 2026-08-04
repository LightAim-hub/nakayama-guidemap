# -*- coding: utf-8 -*-
"""なかやま商店街マップ v2 — 実座標データセット生成 + HTML生成
入力 (スクリプトと同じフォルダ): osm_raw2.json / oq3.json / verified_shops.json /
      shops_geo_osm.json / store_addresses_geo.json / new_shops_geo.json / template.html
通常出力: mapdata.json (中間) と リポジトリ直下の index.html / v2.html
preview出力: リポジトリ直下の preview.html (本番2ファイルは非変更)
実行: python tools/v2-build/build_mapdata.py [--preview] (どこから実行してもよい)
"""
import argparse, json, math, os, re, sys, unicodedata
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
def P(name):
    return os.path.join(HERE, name)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--preview', action='store_true', help='preview専用データとテンプレートでpreview.htmlだけを生成')
parser.add_argument('--allow-shop-change', action='store_true',
                    help='店の増減を承知の上で生成する (お店を追加・削除した時に付ける)')
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

# 2026-08-04: 公式サイトに載っているのに地図に無かった2店 (ネルソンコーヒー中山本店・
# 整骨院リリーフ) を追加して 61 → 63。過去の版から作り直せるよう、旧い数も許す。
PRODUCTION_SHOP_COUNT = 63
PRODUCTION_SIGNAL_COUNT = 11
PRODUCTION_MIGRATION_SHOP_COUNTS = {60, 61, PRODUCTION_SHOP_COUNT}
PRODUCTION_MIGRATION_SIGNAL_COUNTS = {13, PRODUCTION_SIGNAL_COUNT}
SIGNAL_MERGE_DISTANCE_M = 30.0
SLOPE_TOP_NAME = '中山の坂の上'

# ---------------- 掲載名・リンクを公式サイトに合わせる (2026-08-04 実測) ----------------
# 公式 nakayaman.com の各ページを実ブラウザで開き、見出し(h1)と突き合わせた結果の差分。
# 店名の誤記は掲載される側の信用に関わるので、公式の表記を正とする。
# 生成側にも凍結ベース側にも同じ表を当てるので、何度実行しても結果は変わらない。
OFFICIAL_NAME_FIX = {
    '志摩整骨院':       '志摩接骨院',        # 施術所名そのものなので誤記不可
    'ウエルシア薬局':   'ウエルシア仙台中山店',
    '河北仙販 中山支店': '河北仙販中山店',
    'cake NAO':         'Cake NAO',
    '尚絅教会':         '日本パブテスト尚絅教会',
    'サトー商会':       'サトー商会 荒巻店',
    'みなとや':         'みなとや 精肉店',
}
# 地図の上に出す短い呼び名。正式名称が長いと隣の店の名前まで押し出して消してしまう
# (2026-08-04: ウエルシア仙台中山店 に直したら、既定ズームで名前が出なくなった)。
# 一覧・詳細・読み上げは正式名称のままにして、地図の文字だけ短くする。
MAP_LABEL_SHORT = {
    'ウエルシア仙台中山店': 'ウエルシア',
    '日本パブテスト尚絅教会': '尚絅教会',
    'ネルソンコーヒー中山本店': 'ネルソンコーヒー',
}
OFFICIAL_URL_FIX = {
    # 2026-08-04 実測で 404。公式サイトマップにも無い (ページごと消えている)。
    '志摩接骨院':       'https://www.nakayaman.com/post/%E5%BF%97%E6%91%A9%E6%95%B4%E9%AA%A8%E9%99%A2',
    'ビバホーム荒巻店': '#',
    # 4丁目には専用ページがあるのに、5丁目のページへ飛ばしていた。
    'Double Egg4丁目': 'https://www.nakayaman.com/post/double-egg-4%E4%B8%81%E7%9B%AE',
}


def revert_official_fixes(shop_list):
    """凍結ベース(前回の生成物)には公式表記が入っている。座標や対応表は
    すべて内部の元の名前で引いているので、読み込んだ時点で内部名へ戻す。"""
    back = {v: k for k, v in OFFICIAL_NAME_FIX.items()}
    for sh in shop_list:
        if sh['name'] in back:
            sh['name'] = back[sh['name']]


def apply_official_fixes(shop_list, label=None):
    """公式表記へ寄せる。すでに直っているものは触らない。"""
    renamed, relinked = [], []
    for sh in shop_list:
        new = OFFICIAL_NAME_FIX.get(sh['name'])
        if new:
            renamed.append('%s→%s' % (sh['name'], new))
            sh['name'] = new
        url = OFFICIAL_URL_FIX.get(sh['name'])
        if url is not None and sh.get('url') != url:
            relinked.append(sh['name'])
            sh['url'] = url
        short = MAP_LABEL_SHORT.get(sh['name'])
        if short:
            sh['short'] = short
        else:
            sh.pop('short', None)
    if label and (renamed or relinked):
        print('公式表記に合わせた (%s): 店名%d件 %s / リンク%d件 %s'
              % (label, len(renamed), ' / '.join(renamed), len(relinked), ' / '.join(relinked)))
    return renamed, relinked


# 通常ビルドは、現在の本番mapdataを位置修正前の凍結ベースとして使う。
# preview側で増えた道路・信号・meta・店舗付帯情報を本番へ混ぜないための境界。
PRODUCTION_BASELINE = None
if not ARGS.preview:
    with open(P('mapdata.json'), encoding='utf-8') as f:
        PRODUCTION_BASELINE = json.load(f)
    revert_official_fixes(PRODUCTION_BASELINE.get('shops', []))
    _baseline_shop_count = len(PRODUCTION_BASELINE.get('shops', []))
    _baseline_road_count = len(PRODUCTION_BASELINE.get('roads', []))
    _baseline_signal_count = len(PRODUCTION_BASELINE.get('signals', []))
    if (_baseline_shop_count not in PRODUCTION_MIGRATION_SHOP_COUNTS or
            not 62 <= _baseline_road_count <= 78 or
            _baseline_signal_count not in PRODUCTION_MIGRATION_SIGNAL_COUNTS):
        raise SystemExit(
            'production baseline guard failed: expected shops=60|61 roads=62..78 signals=13|11')
    if (_baseline_shop_count == PRODUCTION_SHOP_COUNT and
            not any(sh.get('name') == SLOPE_TOP_NAME
                    for sh in PRODUCTION_BASELINE.get('shops', []))):
        raise SystemExit('production baseline guard failed: 61st shop is not 中山の坂の上')

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
osm_pois = json.load(open(P('osm_pois.json'), encoding='utf-8')).get('elements', [])

# Task K: OSM名寄せは候補抽出を一般化するが、座標採用は確認済み3要素だけに閉じる。
# 同名・部分一致が複数なら採用しない。未確認候補を自動採用しない。
_OSM_POI_TAGS = {'shop', 'amenity', 'office', 'healthcare', 'craft'}
_OSM_CONFIRMED = {
    'ウエルシア薬局': ('node', 5267545834),
    'ん daccha とこや': ('way', 1464243264),
    'Double Egg5丁目': ('node', 5267545823),
}
_OSM_DROP_RE = re.compile(r'[\s・（）()【】「」,、.。/\-ー]+')

def normalize_osm_name(value):
    value = unicodedata.normalize('NFKC', value or '').lower()
    for corporate in ('株式会社', '有限会社', '合同会社'):
        value = value.replace(corporate, '')
    return _OSM_DROP_RE.sub('', value)

def osm_poi_point(element):
    point = element.get('center', element)
    return point.get('lat'), point.get('lon')

def match_unique_osm_poi(shop_name):
    target = normalize_osm_name(shop_name)
    named = []
    for element in osm_pois:
        tags = element.get('tags', {})
        if not tags.get('name') or not (_OSM_POI_TAGS & set(tags)):
            continue
        candidate = normalize_osm_name(tags['name'])
        if candidate:
            named.append((element, candidate))
    exact = [element for element, candidate in named if candidate == target]
    if exact:
        return exact[0] if len(exact) == 1 else None
    partial = [element for element, candidate in named
               if min(len(target), len(candidate)) >= 4 and
               (target in candidate or candidate in target)]
    return partial[0] if len(partial) == 1 else None

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

# 同一住所で個別ピンが確認できなかった組だけ、紙マップの上下順を座標へ焼き込む。
# Task K では出典を表す src と分離操作を切り離し、後段で元の出典へ戻す。
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

# Task K-1: 分離のために動かした事実で src (座標出典) を上書きしない。
_TASK_K_SPREAD_NAMES = {
    'BAKERY&BAKE EndRoll', 'cake NAO', 'Double Egg5丁目', '佐藤次夫税理士事務所',
    'ん daccha とこや', '中杜建設', 'サトー商会', 'みなとや',
    'デイサービス はるの風', '遊季ガーデン',
}
for _shop in shops:
    if _shop['name'] in _TASK_K_SPREAD_NAMES:
        _shop['src'] = 'gsi_addr'

# Task K-2: 確認済み3店だけを OSM の真座標へ置換する。
# この後の共通処理が建物寄せを行い、続く Task I の反復が分離を解き直す。
_task_k_osm_applied = set()
for _shop in shops:
    expected_ = _OSM_CONFIRMED.get(_shop['name'])
    if not expected_:
        continue
    matched_ = match_unique_osm_poi(_shop['name'])
    if not matched_ or (matched_.get('type'), matched_.get('id')) != expected_:
        raise SystemExit('Task K: confirmed OSM POI did not match uniquely: %s' % _shop['name'])
    lat_, lon_ = osm_poi_point(matched_)
    if lat_ is None or lon_ is None:
        raise SystemExit('Task K: confirmed OSM POI has no point: %s' % _shop['name'])
    _shop['lat'], _shop['lng'], _shop['src'] = lat_, lon_, 'osm:exact'
    _task_k_osm_applied.add(_shop['name'])
if _task_k_osm_applied != set(_OSM_CONFIRMED):
    raise SystemExit('Task K: confirmed OSM POI set incomplete')

# モニュメント (紙マップ: 坂の登り口・多夢多夢舎の東の道路沿い) — 位置は概算
shops.append({'name': '商店街モニュメント', 'cat': 'place', 'url': '#', 'voices': [],
              'note': '中山の坂の登り口にあるモニュメントが商店街への目印です！',
              'addr': '', 'lat': 38.28810, 'lng': 140.84642, 'src': 'approx'})

# たきみち公園 (紙マップ右下・OSM公園ポリゴン実在) — タップ可能スポットとして追加
shops.append({'name': 'たきみち公園', 'cat': 'place', 'url': '#', 'voices': [],
              'note': '', 'addr': '', 'lat': 38.291917, 'lng': 140.85282, 'src': 'osm:exact'})

# 公開用スポット写真。preview で確認済みの内容を本番データへ昇格する。
SPOT_PHOTOS = {
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
for sh in shops:
    photos = SPOT_PHOTOS.get(sh['name'])
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
    'name': SLOPE_TOP_NAME, 'cat': 'place', 'url': '#', 'voices': [],
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

def segment_projection(p, a, b):
    """Return (distance, nearest point) on segment a-b."""
    dx, dy = b[0]-a[0], b[1]-a[1]
    den = dx*dx + dy*dy
    t = 0.0 if den <= 1e-12 else max(0.0, min(1.0,
        ((p[0]-a[0])*dx + (p[1]-a[1])*dy) / den))
    q = (a[0] + t*dx, a[1] + t*dy)
    return math.hypot(p[0]-q[0], p[1]-q[1]), q

def polygon_bbox(poly):
    return (min(p[0] for p in poly), min(p[1] for p in poly),
            max(p[0] for p in poly), max(p[1] for p in poly))

def bbox_distance(p, bbox):
    return math.hypot(max(bbox[0]-p[0], 0.0, p[0]-bbox[2]),
                      max(bbox[1]-p[1], 0.0, p[1]-bbox[3]))

def point_in_polygon(p, poly):
    """Boundary-inclusive even/odd test for an OSM building ring."""
    for a, b in zip(poly, poly[1:] + poly[:1]):
        if segment_projection(p, a, b)[0] <= 1e-7:
            return True
    x, y = p
    inside = False
    for a, b in zip(poly, poly[1:] + poly[:1]):
        if ((a[1] > y) != (b[1] > y) and
                x < (b[0]-a[0]) * (y-a[1]) / ((b[1]-a[1]) or 1e-30) + a[0]):
            inside = not inside
    return inside

def polygon_boundary_distance(p, poly):
    return min(segment_projection(p, a, b)[0]
               for a, b in zip(poly, poly[1:] + poly[:1]))

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
    # Task I は毎回、入力JSONから組み立てた座標を正本にする。前回の生成物を
    # 位置入力へ自己参照しないよう、生成直後の店舗を凍結しておく。
    _task_i_fresh_shops = json.loads(json.dumps(shops, ensure_ascii=False))
    generated_names = {sh['name'] for sh in shops}
    baseline_names = {sh['name'] for sh in PRODUCTION_BASELINE['shops']}
    if generated_names != baseline_names | {SLOPE_TOP_NAME}:
        # 2026-08-04: 店が1件でも増減するとここで落ち、組合側で更新できなかった。
        # 「気づかずに変わる」のを止めるのが目的なので、意図した変更は
        #   python tools/v2-build/build_mapdata.py --allow-shop-change
        # で通す。差分は必ず表示して、黙って変わらないようにする。
        added = sorted(generated_names - (baseline_names | {SLOPE_TOP_NAME}))
        removed = sorted((baseline_names | {SLOPE_TOP_NAME}) - generated_names)
        print('店の増減を検出: 追加=%s / 削除=%s' % (added or 'なし', removed or 'なし'))
        if not ARGS.allow_shop_change:
            raise SystemExit('店が増減しています。意図した変更なら --allow-shop-change を付けて実行してください。')
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
    if ((len(shops) != PRODUCTION_SHOP_COUNT and not ARGS.allow_shop_change)
            or not 62 <= len(roads) <= 78
            or len(signals) not in PRODUCTION_MIGRATION_SIGNAL_COUNTS):
        raise SystemExit('production output guard failed: expected shops=%d roads=62..78 signals=13|11'
                         % PRODUCTION_SHOP_COUNT)
    print('production compatibility geometry: shops=61 roads=%d baseline_signals=%d' %
          (len(roads), len(signals)))

    # ---------------- Task I: 歩行者が使える本番ジオメトリ ----------------
    # 店の真座標は毎回ローカル入力JSONから再生成した値へ戻す。mapdata.json は
    # 前回ビルドの生成物なので、座標の入力としては使わない。
    _task_i_fresh_by_name = {sh['name']: sh for sh in _task_i_fresh_shops}
    shops = json.loads(json.dumps(PRODUCTION_BASELINE['shops'], ensure_ascii=False))
    for sh in shops:
        fresh = _task_i_fresh_by_name[sh['name']]
        for key in ('x', 'y', 'tx', 'ty', 'padr', 'clamped', 'far_m', 'far_deg', 'hint'):
            sh.pop(key, None)
        for key in ('lat', 'lng', 'src', 'addr', 'clamped', 'far_m', 'far_deg', 'hint'):
            if key in fresh:
                sh[key] = fresh[key]
        if fresh.get('photos'):
            sh['photos'] = json.loads(json.dumps(fresh['photos'], ensure_ascii=False))
        else:
            sh.pop('photos', None)
        sh['x'], sh['y'] = fresh['x'], fresh['y']
        sh['tx'], sh['ty'] = fresh.get('tx', fresh['x']), fresh.get('ty', fresh['y'])
    if SLOPE_TOP_NAME not in baseline_names:
        shops.append(json.loads(json.dumps(_task_i_fresh_by_name[SLOPE_TOP_NAME],
                                          ensure_ascii=False)))
    # 2026-08-04: 入力側に足した店が、凍結ベースからの組み直しで落ちていた
    # (中山の坂の上 だけを名指しで拾う書き方になっていた)。名指しをやめて、
    # 凍結ベースに無い店はすべて拾う。--allow-shop-change を付けた時だけ通る。
    _added_now = [n for n in sorted(generated_names - set(sh['name'] for sh in shops))]
    if _added_now:
        if not ARGS.allow_shop_change:
            raise SystemExit('入力に新しい店がある: %s (--allow-shop-change が要る)' % _added_now)
        for n in _added_now:
            shops.append(json.loads(json.dumps(_task_i_fresh_by_name[n], ensure_ascii=False)))
        print('地図に載せた新しい店: %s' % ' / '.join(_added_now))
    if len(shops) != PRODUCTION_SHOP_COUNT and not ARGS.allow_shop_change:
        raise SystemExit('production shop guard failed after adding 中山の坂の上')

    # 住所の枝番表記だけが異なる同一施設は、ゲートと同じ住所由来グループへ正規化する。
    # 店名・表示文言は変えず、分離制約の入力だけを一意にする。
    _task_i_by_name_fresh = {sh['name']: sh for sh in shops}
    _task_i_by_name_fresh['遊季ガーデン']['addr'] = '仙台市青葉区中山5-11-3'

    # 信号で不足していた実在交差道だけを追加する。荒巻泉線と川平二丁目1号線は
    # 既存の短い断片を同じOSM wayの全形状へ置換するので、本数増には数えない。
    _task_i_way_ids = {
        32589764, 103695689, 103697723, 103842638, 1017764844, 1464036340,
    }
    _task_i_replace_names = {'荒巻泉線', '川平二丁目１号線'}
    roads = [json.loads(json.dumps(r, ensure_ascii=False))
             for r in PRODUCTION_BASELINE['roads']
             if not r.get('task_i_source_id') and r.get('name') not in _task_i_replace_names]
    _task_i_roads_before = 62
    _task_i_raw_by_id = {e.get('id'): e for e in raw.get('elements', [])}
    for way_id in sorted(_task_i_way_ids):
        e = _task_i_raw_by_id.get(way_id)
        if not e or e.get('type') != 'way' or not e.get('geometry'):
            raise SystemExit('Task I road way missing from osm_raw2.json: %s' % way_id)
        hw = e.get('tags', {}).get('highway')
        if hw not in CLASS_MAP:
            raise SystemExit('Task I road way has unsupported highway: %s %s' % (way_id, hw))
        cls = 'spine' if e.get('tags', {}).get('name') in SPINE_ROAD_NAMES else CLASS_MAP[hw]
        if cls not in ('minor', 'mid', 'major', 'spine'):
            raise SystemExit('Task I selected road is not a rendered vehicle road: %s %s' % (way_id, cls))
        pts_ = []
        for q in e['geometry']:
            gx, gy = project(q['lat'], q['lon'])
            wx, wy = wobble(gx - minx, gy - miny)
            pts_.append([round(wx, 1), round(wy, 1)])
        roads.append({
            'cls': cls, 'name': e.get('tags', {}).get('name', ''),
            'guide_spine': cls == 'spine', 'pts': pts_, 'task_i_source_id': way_id,
        })
    if len(roads) > 78 or len(roads) - _task_i_roads_before > 16:
        raise SystemExit('Task I road-count guard failed: before=62 after=%d' % len(roads))

    # 手置き2基を落とし、OSM traffic_signals ノードだけを1対1で使う。
    # baseline は移行前の生座標13点と統合後の中点11点のどちらも受ける。
    # 統合中点から閾値の半分以内にある生ノードを復元し、丸め誤差0.6mを許容する。
    # required 2基は、さらに古い11点baselineからの移行互換として残す。
    _task_i_manual_signals = {(403.6, 272.2), (490.9, 482.5)}
    _task_i_required_signal_ids = {10309219409, 13831368321}
    _task_i_baseline_signal_points = [tuple(p) for p in PRODUCTION_BASELINE['signals']
                                      if tuple(p) not in _task_i_manual_signals]
    _task_i_signal_rows = []
    for e in _sig_raw.get('elements', []):
        if e.get('lat') is None or e.get('tags', {}).get('highway') != 'traffic_signals':
            continue
        sx, sy = project(e['lat'], e['lon'])
        pxy = (round(sx - minx, 1), round(sy - miny, 1))
        existed = any(math.hypot(pxy[0]-q[0], pxy[1]-q[1]) <=
                      SIGNAL_MERGE_DISTANCE_M / 2 + 0.6
                      for q in _task_i_baseline_signal_points)
        if existed or e.get('id') in _task_i_required_signal_ids:
            _task_i_signal_rows.append((e.get('id'), pxy))
    _task_i_signal_rows.sort()
    _task_i_raw_signal_points = [p for _, p in _task_i_signal_rows]
    if (len(_task_i_raw_signal_points) != 13 or
            len(set(_task_i_raw_signal_points)) != 13):
        raise SystemExit('Task I signal 1:1 guard failed: expected 13 unique OSM nodes')

    # 同じ交差点の両側にある信号は歩行者向け地図では1基の目印として扱う。
    # ボス実測で重複に見えた2組が17.1m/19.6mだったため、30m未満を同一交差点とする。
    _signal_parent = list(range(len(_task_i_signal_rows)))

    def _signal_find(index_):
        while _signal_parent[index_] != index_:
            _signal_parent[index_] = _signal_parent[_signal_parent[index_]]
            index_ = _signal_parent[index_]
        return index_

    def _signal_union(a_, b_):
        root_a_, root_b_ = _signal_find(a_), _signal_find(b_)
        if root_a_ != root_b_:
            _signal_parent[root_b_] = root_a_

    for i_, (_, point_) in enumerate(_task_i_signal_rows):
        for j_ in range(i_ + 1, len(_task_i_signal_rows)):
            other_ = _task_i_signal_rows[j_][1]
            if math.dist(point_, other_) < SIGNAL_MERGE_DISTANCE_M:
                _signal_union(i_, j_)

    _signal_groups = defaultdict(list)
    for i_, row_ in enumerate(_task_i_signal_rows):
        _signal_groups[_signal_find(i_)].append(row_)
    _task_i_signal_display_rows = []
    for members_ in sorted(_signal_groups.values(), key=lambda rows_: min(row_[0] for row_ in rows_)):
        ids_ = tuple(sorted(row_[0] for row_ in members_))
        point_ = (
            round(sum(row_[1][0] for row_ in members_) / len(members_), 1),
            round(sum(row_[1][1] for row_ in members_) / len(members_), 1),
        )
        _task_i_signal_display_rows.append((ids_, point_))

    signals = [[point_[0], point_[1]] for _, point_ in _task_i_signal_display_rows]
    _merged_signal_nodes = sum(len(ids_) - 1 for ids_, _ in _task_i_signal_display_rows)
    _remaining_near_signal_pairs = [
        (signals[i_], signals[j_], round(math.dist(signals[i_], signals[j_]), 1))
        for i_ in range(len(signals)) for j_ in range(i_ + 1, len(signals))
        if math.dist(signals[i_], signals[j_]) < SIGNAL_MERGE_DISTANCE_M
    ]
    if (len(signals) != PRODUCTION_SIGNAL_COUNT or _merged_signal_nodes != 2 or
            _remaining_near_signal_pairs):
        raise SystemExit(
            'signal merge guard failed: displayed=%d merged=%d remaining_near=%s' %
            (len(signals), _merged_signal_nodes, _remaining_near_signal_pairs))

    # 既存の本番spineは変更しない。N5の東西判定も同じ正本を使う。
    busway = json.loads(json.dumps(PRODUCTION_BASELINE['busway'], ensure_ascii=False))
    meta = json.loads(json.dumps(PRODUCTION_BASELINE['meta'], ensure_ascii=False))

    def _task_i_poly_inside(poly_, point_):
        x_, y_ = point_
        inside_ = False
        for a_, b_ in zip(poly_, poly_[1:] + poly_[:1]):
            if (a_[1] > y_) != (b_[1] > y_):
                if x_ < a_[0] + (y_ - a_[1]) / (b_[1] - a_[1]) * (b_[0] - a_[0]):
                    inside_ = not inside_
        return inside_

    def _task_i_seg_distance(point_, a_, b_):
        dx_, dy_ = b_[0]-a_[0], b_[1]-a_[1]
        den_ = dx_*dx_ + dy_*dy_
        t_ = 0.0 if den_ <= 1e-12 else max(0.0, min(1.0,
            ((point_[0]-a_[0])*dx_ + (point_[1]-a_[1])*dy_) / den_))
        return math.hypot(point_[0]-(a_[0]+t_*dx_), point_[1]-(a_[1]+t_*dy_))

    def _task_i_poly_edge_distance(poly_, point_):
        return min(_task_i_seg_distance(point_, a_, b_)
                   for a_, b_ in zip(poly_, poly_[1:] + poly_[:1]))

    def _task_i_road_distance(point_, road_):
        return min(_task_i_seg_distance(point_, a_, b_)
                   for a_, b_ in zip(road_['pts'], road_['pts'][1:]))

    def _task_i_spine_x(y_):
        best_ = None
        for a_, b_ in zip(busway[1], busway[1][1:]):
            lo_, hi_ = sorted((a_[1], b_[1]))
            if lo_ <= y_ <= hi_:
                t_ = 0.0 if b_[1] == a_[1] else (y_ - a_[1]) / (b_[1] - a_[1])
                return a_[0] + t_ * (b_[0] - a_[0])
            for p_ in (a_, b_):
                cand_ = (abs(y_ - p_[1]), p_[0])
                if best_ is None or cand_ < best_:
                    best_ = cand_
        return best_[1]

    def _task_i_side(point_):
        return 1 if point_[0] >= _task_i_spine_x(point_[1]) else -1

    def _task_i_street_axis(y_):
        h_ = 2.0
        ax_ = _task_i_spine_x(y_ + h_) - _task_i_spine_x(y_ - h_)
        ay_ = 2.0 * h_
        length_ = math.hypot(ax_, ay_) or 1.0
        return ax_ / length_, ay_ / length_

    _task_i_by_addr = {}
    for sh in shops:
        if sh.get('addr'):
            _task_i_by_addr.setdefault(sh['addr'], []).append(sh)
    _task_i_same_address_groups = []
    for addr_, members_ in _task_i_by_addr.items():
        if len(members_) < 2:
            continue
        cx_ = sum(sh['tx'] for sh in members_) / len(members_)
        cy_ = sum(sh['ty'] for sh in members_) / len(members_)
        if max(math.hypot(sh['tx']-cx_, sh['ty']-cy_) for sh in members_) <= 40.0:
            _task_i_same_address_groups.append((addr_, [sh['name'] for sh in members_]))
    _task_i_paired_names = {
        name_ for _, names_ in _task_i_same_address_groups for name_ in names_
    }
    _task_i_along_limits = {'osm:exact': 4.0, 'osm:partial': 4.0,
                            'gsi_addr': 8.0, 'approx': 8.0}
    _task_i_cross_limits = {'osm:exact': 20.0, 'osm:partial': 20.0,
                            'gsi_addr': 20.0, 'approx': 25.0}

    def _task_i_move_components(shop_, point_):
        dx_, dy_ = point_[0]-shop_['tx'], point_[1]-shop_['ty']
        ax_, ay_ = _task_i_street_axis(shop_['ty'])
        return abs(dx_*ax_ + dy_*ay_), abs(dx_*ay_ - dy_*ax_)

    def _task_i_move_axis_safe(shop_, point_):
        along_, cross_ = _task_i_move_components(shop_, point_)
        src_ = shop_.get('src', 'approx')
        if cross_ > _task_i_cross_limits.get(src_, 25.0) + 1e-9:
            return False
        return (shop_['name'] in _task_i_paired_names or
                along_ <= _task_i_along_limits.get(src_, 8.0) + 1e-9)

    def _task_i_park_relation_safe(shop_, point_):
        true_ = (shop_['tx'], shop_['ty'])
        return all(_task_i_poly_inside(pk_['pts'], true_) ==
                   _task_i_poly_inside(pk_['pts'], point_) for pk_ in parks)

    _task_i_road_widths = {'spine': 13.0, 'major': 12.0, 'mid': 9.0, 'minor': 5.0}
    _task_i_anchor_re = re.compile(r'公園|郵便局|中学校|小学校|市民センター|不動尊|ドライブスクール|ヨークベニマル')

    def _task_i_star_radius(shop_):
        return 3.5 if ((shop_.get('voices') or []) or shop_['cat'] == 'place' or
                       _task_i_anchor_re.search(shop_['name'])) else 2.75

    def _task_i_road_safe(shop_, point_):
        setback_ = _task_i_star_radius(shop_)
        for road_ in roads:
            cls_ = 'spine' if road_.get('guide_spine') else road_['cls']
            if _task_i_road_distance(point_, road_) < _task_i_road_widths[cls_] / 2.0 + setback_:
                return False
        return True

    _task_i_buildings = []
    for e in json.load(open(P('buildings_raw.json'), encoding='utf-8')).get('elements', []):
        geom_ = e.get('geometry')
        if not geom_:
            continue
        poly_ = []
        for q_ in geom_:
            if q_.get('lat') is None:
                continue
            gx_, gy_ = project(q_['lat'], q_['lon'])
            poly_.append((gx_ - minx, gy_ - miny))
        if len(poly_) < 3:
            continue
        xs_, ys_ = [p_[0] for p_ in poly_], [p_[1] for p_ in poly_]
        if max(xs_) < -60 or min(xs_) > W+60 or max(ys_) < -60 or min(ys_) > H+60:
            continue
        _task_i_buildings.append((min(xs_), min(ys_), max(xs_), max(ys_), poly_, e.get('id', 0)))

    def _task_i_bbox_distance(building_, point_):
        x0_, y0_, x1_, y1_ = building_[:4]
        dx_ = max(x0_-point_[0], 0, point_[0]-x1_)
        dy_ = max(y0_-point_[1], 0, point_[1]-y1_)
        return math.hypot(dx_, dy_)

    _task_i_interior_cache = {}

    def _task_i_interior_points(building_, min_edge_=2.0):
        bid_ = (building_[5], min_edge_)
        if bid_ in _task_i_interior_cache:
            return _task_i_interior_cache[bid_]
        x0_, y0_, x1_, y1_, poly_, _ = building_
        step_ = 0.5
        points_ = []
        for iy_ in range(math.ceil(y0_/step_), math.floor(y1_/step_)+1):
            y_ = iy_ * step_
            for ix_ in range(math.ceil(x0_/step_), math.floor(x1_/step_)+1):
                point_ = (ix_*step_, y_)
                if (_task_i_poly_inside(poly_, point_) and
                        _task_i_poly_edge_distance(poly_, point_) >= min_edge_):
                    points_.append(point_)
        _task_i_interior_cache[bid_] = points_
        return points_

    _task_i_open_sites = {
        'たきみち公園', 'なかやまとびのこ公園', '中山山の神公園',
        '中山小学校', '中山中学校', '中山ドライブスクール',
        '中山鳥瀧不動尊（目の神様）', '商店街モニュメント', SLOPE_TOP_NAME,
    }
    _task_i_candidate_cache = {}

    def _task_i_candidates(shop_, limit_=120, relax_edge_=False):
        cache_key_ = (shop_['name'], limit_, relax_edge_)
        if cache_key_ in _task_i_candidate_cache:
            return _task_i_candidate_cache[cache_key_]
        origin_ = (shop_['tx'], shop_['ty'])
        side_ = _task_i_side(origin_)
        found_ = []
        if shop_['name'] in _task_i_open_sites:
            if (_task_i_road_safe(shop_, origin_) and
                    _task_i_move_axis_safe(shop_, origin_) and
                    _task_i_park_relation_safe(shop_, origin_)):
                found_.append((0.0, origin_, None))
            else:
                seen_ = set()
                for ring_ in range(81):
                    radius_ = ring_ * 0.5
                    samples_ = 1 if ring_ == 0 else max(12, int(2*math.pi*radius_/0.5))
                    for i_ in range(samples_):
                        angle_ = 2*math.pi*i_/samples_
                        point_ = (round((origin_[0]+radius_*math.cos(angle_))*2)/2,
                                  round((origin_[1]+radius_*math.sin(angle_))*2)/2)
                        if point_ in seen_:
                            continue
                        seen_.add(point_)
                        if (_task_i_side(point_) == side_ and
                                _task_i_road_safe(shop_, point_) and
                                _task_i_move_axis_safe(shop_, point_) and
                                _task_i_park_relation_safe(shop_, point_)):
                            found_.append((math.dist(origin_, point_), point_, None))
                    found_.sort(key=lambda row_: (row_[0], row_[1][1], row_[1][0]))
                    if len(found_) >= limit_ and found_[limit_-1][0] < radius_:
                        break
        else:
            ordered_ = sorted(_task_i_buildings,
                              key=lambda b_: (_task_i_bbox_distance(b_, origin_), b_[5]))
            # 既に建物内かつ道路から安全な店は動かさない。
            for b_ in ordered_:
                if _task_i_bbox_distance(b_, origin_) > 0:
                    break
                if (_task_i_poly_inside(b_[4], origin_) and
                        _task_i_road_safe(shop_, origin_) and
                        _task_i_move_axis_safe(shop_, origin_) and
                        _task_i_park_relation_safe(shop_, origin_)):
                    found_.append((0.0, origin_, b_[5]))
                    break
            best_ = 1e9
            for b_ in ordered_:
                lower_ = _task_i_bbox_distance(b_, origin_)
                found_.sort(key=lambda row_: (row_[0], row_[1][1], row_[1][0], str(row_[2])))
                if len(found_) >= limit_ and lower_ > found_[limit_-1][0] + 1.0:
                    break
                if shop_['name'] in _task_i_paired_names:
                    if lower_ > 40.0:
                        break
                elif lower_ > best_ + 8.0:
                    break
                min_edge_ = 0.1 if (relax_edge_ or shop_['name'] in _task_i_paired_names) else 2.0
                for point_ in _task_i_interior_points(b_, min_edge_):
                    if (_task_i_side(point_) != side_ or
                            not _task_i_road_safe(shop_, point_) or
                            not _task_i_move_axis_safe(shop_, point_) or
                            not _task_i_park_relation_safe(shop_, point_)):
                        continue
                    dist_ = math.dist(origin_, point_)
                    found_.append((dist_, point_, b_[5]))
                    best_ = min(best_, dist_)
                if found_:
                    found_ = sorted(found_, key=lambda row_: (row_[0], row_[1][1], row_[1][0], str(row_[2])))[:limit_]
        found_ = sorted(found_, key=lambda row_: (row_[0], row_[1][1], row_[1][0], str(row_[2])))[:limit_]
        if not found_:
            raise SystemExit('Task I: no building/road-safe position for %s' % shop_['name'])
        _task_i_candidate_cache[cache_key_] = found_
        return found_

    _task_i_all_candidates = {sh['name']: _task_i_candidates(sh) for sh in shops}

    _task_i_by_name = {sh['name']: sh for sh in shops}
    _task_i_positions = {name_: rows_[0][1] for name_, rows_ in _task_i_all_candidates.items()}
    _task_i_building_ids = {name_: rows_[0][2] for name_, rows_ in _task_i_all_candidates.items()}

    # 連成制約を解いた安定解を真座標からの相対量として再現する。絶対座標の自己参照ではなく、
    # 毎回ローカル入力から得た tx/ty に加算し、後段で建物・道路・方向・分離を再検査する。
    _task_i_preferred_offsets = {
        # Task K: OSM真座標を入れた密集帯10店を建物候補上で同時に解いた相対初期解。
        # 後段で建物内・道路外・東西・南北順・8.5m分離・N10を全件再検査する。
        'ん daccha とこや': (-2.4, 0.3),
        '中山不動産': (4.3, -5.9),
        '中杜建設': (24.8, 0.1),
        '花祭壇': (-15.0, 5.2),
        'ダイニングバー 祭': (1.2, -1.1),
        '佐藤次夫税理士事務所': (2.9, -7.1),
        'おたからや': (3.4, -1.4),
        'Double Egg5丁目': (1.8, 3.2),
        'お菜とお酒アイリス': (0.1, 0.2),
        '藤倉設備工業': (-3.3, 0.8),
        'デイサービス はるの風': (6.5, 0.2),
        '遊季ガーデン': (-1.5, 0.2),
        '梅原表具店': (5.1, -1.0),
        'BAKERY&BAKE EndRoll': (2.0, -3.9),
        'cake NAO': (1.5, -1.9),
    }
    for name_, (dx_, dy_) in _task_i_preferred_offsets.items():
        shop_ = _task_i_by_name[name_]
        _task_i_positions[name_] = (round(shop_['tx']+dx_, 1), round(shop_['ty']+dy_, 1))
        _task_i_building_ids[name_] = None
    # 同一住所は固定14mペアへ個別処理せず、全店舗共通の8.4m分離ソルバで扱う。
    # これにより3店舗グループも、周辺店との衝突を含めて同じ制約で解ける。
    _task_i_pairs = []
    _task_i_pair_names = {name_ for pair_ in _task_i_pairs for name_ in pair_}
    _task_i_pair_results = []

    def _task_i_along_coord(shop_, point_):
        ax_, ay_ = _task_i_street_axis(shop_['ty'])
        return point_[0]*ax_ + point_[1]*ay_

    _task_i_band = sorted(
        [sh for sh in shops if abs(sh['tx']-_task_i_spine_x(sh['ty'])) < 60.0],
        key=lambda sh: sh['ty'],
    )
    _task_i_n10_pairs = []
    for a_, b_ in zip(_task_i_band, _task_i_band[1:]):
        if a_['name'] in _task_i_paired_names and b_['name'] in _task_i_paired_names:
            continue
        true_gap_ = abs(_task_i_along_coord(a_, (a_['tx'], a_['ty'])) -
                        _task_i_along_coord(b_, (b_['tx'], b_['ty'])))
        _task_i_n10_pairs.append((a_, b_, true_gap_))

    def _task_i_n10_candidate_ok(name_, point_):
        for a_, b_, true_gap_ in _task_i_n10_pairs:
            if name_ not in (a_['name'], b_['name']):
                continue
            pa_ = point_ if a_['name'] == name_ else _task_i_positions[a_['name']]
            pb_ = point_ if b_['name'] == name_ else _task_i_positions[b_['name']]
            shown_gap_ = abs(_task_i_along_coord(a_, pa_) - _task_i_along_coord(b_, pb_))
            if abs(shown_gap_-true_gap_) > 6.0 + 1e-9:
                return False
        return True

    def _task_i_separated_from_others(name_, point_, excluded_):
        for other_name_, other_point_ in _task_i_positions.items():
            if other_name_ == name_ or other_name_ in excluded_:
                continue
            if math.dist(point_, other_point_) < 8.4 - 1e-9:
                return False
        return True

    for upper_name_, lower_name_ in _task_i_pairs:
        upper_ = _task_i_by_name[upper_name_]
        lower_ = _task_i_by_name[lower_name_]
        # 同住所ペアは同一候補棟の細い輪郭内で14mを作る場合があるため、
        # 最寄り一点だけでなく近傍グリッドを十分に保持して組み合わせる。
        upper_limit_ = 1000
        lower_limit_ = 1000
        matches_ = []
        for a_ in _task_i_candidates(upper_, upper_limit_):
            for b_ in _task_i_candidates(lower_, lower_limit_):
                separation_ = math.dist(a_[1], b_[1])
                if a_[1][1] < b_[1][1] and separation_ >= 8.4 - 1e-9:
                    matches_.append((a_[0]+b_[0], abs(separation_-14.0),
                                     a_[1][1], a_[1][0], b_[1][1], b_[1][0],
                                     separation_, a_, b_))
        if not matches_:
            upper_rows_ = _task_i_candidates(upper_, upper_limit_)
            lower_rows_ = _task_i_candidates(lower_, lower_limit_)
            upper_ok_ = [r_ for r_ in upper_rows_
                         if _task_i_separated_from_others(upper_name_, r_[1],
                                                           {upper_name_, lower_name_})]
            lower_ok_ = [r_ for r_ in lower_rows_
                         if _task_i_separated_from_others(lower_name_, r_[1],
                                                           {upper_name_, lower_name_})]
            def _task_i_best_clearance(rows_, name_, excluded_):
                scored_ = []
                for r_ in rows_:
                    near_ = min((math.dist(r_[1], q_), other_)
                                for other_, q_ in _task_i_positions.items()
                                if other_ != name_ and other_ not in excluded_)
                    scored_.append((near_[0], near_[1], r_[1]))
                return max(scored_, default=(0.0, '', (0.0, 0.0)))
            raise SystemExit('Task I: same-address pair has no feasible separated points: %s / %s' %
                             (upper_name_, lower_name_) +
                             ' candidates=%d/%d n10=%d/%d separated=%d/%d feasible=%d/%d best=%s/%s' %
                             (len(upper_rows_), len(lower_rows_),
                              sum(_task_i_n10_candidate_ok(upper_name_, r_[1]) for r_ in upper_rows_),
                              sum(_task_i_n10_candidate_ok(lower_name_, r_[1]) for r_ in lower_rows_),
                              sum(_task_i_separated_from_others(upper_name_, r_[1], {upper_name_, lower_name_}) for r_ in upper_rows_),
                              sum(_task_i_separated_from_others(lower_name_, r_[1], {upper_name_, lower_name_}) for r_ in lower_rows_),
                              len(upper_ok_), len(lower_ok_),
                              _task_i_best_clearance(upper_rows_, upper_name_, {upper_name_, lower_name_}),
                              _task_i_best_clearance(lower_rows_, lower_name_, {upper_name_, lower_name_})))
        best_pair_ = min(matches_)
        a_, b_ = best_pair_[-2], best_pair_[-1]
        _task_i_positions[upper_name_], _task_i_positions[lower_name_] = a_[1], b_[1]
        _task_i_building_ids[upper_name_], _task_i_building_ids[lower_name_] = a_[2], b_[2]
        _task_i_pair_results.append((upper_name_, lower_name_, best_pair_[6]))

    def _task_i_order_inversions():
        inversions_ = []
        for i_, a_ in enumerate(shops):
            for b_ in shops[i_+1:]:
                true_delta_ = a_['ty'] - b_['ty']
                display_delta_ = (_task_i_positions[a_['name']][1] -
                                  _task_i_positions[b_['name']][1])
                if true_delta_ * display_delta_ < 0:
                    inversions_.append((a_['name'], b_['name']))
        return inversions_

    def _task_i_order_candidate_ok(name_, point_):
        shop_ = _task_i_by_name[name_]
        for other_ in shops:
            if other_ is shop_:
                continue
            true_delta_ = shop_['ty'] - other_['ty']
            display_delta_ = point_[1] - _task_i_positions[other_['name']][1]
            if true_delta_ * display_delta_ < 0:
                return False
        return True

    # 独立スナップで近接店の上下が入れ替わった場合、同一住所ペアを固定したまま
    # 非ペア側の次善候補へ移す。全候補は距離順なので最小追加移動で収束する。
    for _ in range(20):
        inversions_ = _task_i_order_inversions()
        if not inversions_:
            break
        repairs_ = []
        for a_name_, b_name_ in inversions_:
            for name_ in (a_name_, b_name_):
                if name_ in _task_i_pair_names:
                    continue
                shop_ = _task_i_by_name[name_]
                for row_ in _task_i_candidates(shop_, 1000):
                    if _task_i_order_candidate_ok(name_, row_[1]):
                        repairs_.append((row_[0], name_, row_))
                        break
        if not repairs_:
            raise SystemExit('Task I: cannot preserve north/south order: %s' % inversions_)
        _, repair_name_, repair_row_ = min(repairs_, key=lambda row_: (row_[0], row_[1]))
        _task_i_positions[repair_name_] = repair_row_[1]
        _task_i_building_ids[repair_name_] = repair_row_[2]
    if _task_i_order_inversions():
        raise SystemExit('Task I: north/south order did not converge')

    def _task_i_separation_violations(min_sep_=8.5):
        out_ = []
        for i_, a_ in enumerate(shops):
            pa_ = _task_i_positions[a_['name']]
            for b_ in shops[i_+1:]:
                pb_ = _task_i_positions[b_['name']]
                dist_ = math.dist(pa_, pb_)
                if dist_ < min_sep_ - 1e-9:
                    out_.append((dist_, a_['name'], b_['name']))
        return sorted(out_)

    def _task_i_n10_violations():
        out_ = []
        for a_, b_, true_gap_ in _task_i_n10_pairs:
            pa_, pb_ = _task_i_positions[a_['name']], _task_i_positions[b_['name']]
            shown_gap_ = abs(_task_i_along_coord(a_, pa_) -
                             _task_i_along_coord(b_, pb_))
            warp_ = abs(shown_gap_-true_gap_)
            if warp_ > 6.0 + 1e-9:
                out_.append((warp_, a_['name'], b_['name']))
        return sorted(out_, reverse=True)

    def _task_i_n5_violations():
        out_ = []
        for shop_ in _task_i_band:
            pos_ = _task_i_positions[shop_['name']]
            side_ = _task_i_side(pos_)
            true_opp_ = [other_ for other_ in _task_i_band
                         if _task_i_side((other_['tx'], other_['ty'])) !=
                            _task_i_side((shop_['tx'], shop_['ty'])) and
                            abs(other_['ty']-shop_['ty']) < 40.0]
            if not true_opp_:
                continue
            shown_opp_ = [other_ for other_ in _task_i_band
                          if _task_i_side(_task_i_positions[other_['name']]) != side_ and
                          abs(_task_i_positions[other_['name']][1]-pos_[1]) < 40.0]
            if not shown_opp_:
                nearest_ = min(true_opp_, key=lambda other_: abs(other_['ty']-shop_['ty']))
                out_.append((shop_['name'], nearest_['name']))
        return sorted(out_)

    def _task_i_local_n5_ok(name_, point_):
        old_ = _task_i_positions[name_]
        _task_i_positions[name_] = point_
        try:
            return not any(name_ in row_ for row_ in _task_i_n5_violations())
        finally:
            _task_i_positions[name_] = old_

    def _task_i_local_candidate_ok(name_, point_):
        return (_task_i_order_candidate_ok(name_, point_) and
                _task_i_separated_from_others(name_, point_, set()) and
                _task_i_n10_candidate_ok(name_, point_) and
                _task_i_local_n5_ok(name_, point_))

    # 分離と通り沿い間隔を同じ座標集合で反復修復する。沿う方向の上限・建物内・
    # 道路外・公園内外・東西は候補生成時に既にクリップ済み。
    for _task_i_repair_round in range(80):
        sep_bad_ = _task_i_separation_violations()
        n10_bad_ = _task_i_n10_violations()
        n5_bad_ = _task_i_n5_violations()
        if not sep_bad_ and not n10_bad_ and not n5_bad_:
            break
        if sep_bad_:
            _, a_name_, b_name_ = sep_bad_[0]
        elif n10_bad_:
            _, a_name_, b_name_ = n10_bad_[0]
        else:
            a_name_, b_name_ = n5_bad_[0]
        repairs_ = []
        for name_ in (a_name_, b_name_):
            shop_ = _task_i_by_name[name_]
            current_ = _task_i_positions[name_]
            for row_ in _task_i_candidates(shop_, 1000, True):
                if row_[1] == current_ or not _task_i_local_candidate_ok(name_, row_[1]):
                    continue
                repairs_.append((row_[0], name_, row_))
                break
        if not repairs_:
            pair_repairs_ = []
            a_shop_, b_shop_ = _task_i_by_name[a_name_], _task_i_by_name[b_name_]
            a_rows_ = [row_ for row_ in _task_i_candidates(a_shop_, 1000, True)
                       if _task_i_separated_from_others(a_name_, row_[1], {b_name_})]
            b_rows_ = [row_ for row_ in _task_i_candidates(b_shop_, 1000, True)
                       if _task_i_separated_from_others(b_name_, row_[1], {a_name_})]
            old_a_, old_b_ = _task_i_positions[a_name_], _task_i_positions[b_name_]
            for a_row_ in a_rows_:
                for b_row_ in b_rows_:
                    score_ = a_row_[0] + b_row_[0]
                    if math.dist(a_row_[1], b_row_[1]) < 8.5 - 1e-9:
                        continue
                    _task_i_positions[a_name_], _task_i_positions[b_name_] = a_row_[1], b_row_[1]
                    order_bad_ = _task_i_order_inversions()
                    local_n10_bad_ = [row_ for row_ in _task_i_n10_violations()
                                      if a_name_ in row_[1:] or b_name_ in row_[1:]]
                    local_n5_bad_ = [row_ for row_ in _task_i_n5_violations()
                                     if a_name_ in row_ or b_name_ in row_]
                    if not order_bad_ and not local_n10_bad_ and not local_n5_bad_:
                        pair_repairs_ = [(score_, a_row_, b_row_)]
                        break
                if pair_repairs_:
                    break
                _task_i_positions[a_name_], _task_i_positions[b_name_] = old_a_, old_b_
            if not pair_repairs_:
                max_direct_ = max((math.dist(ar_[1], br_[1]) for ar_ in a_rows_ for br_ in b_rows_), default=0.0)
                max_ordered_ = 0.0
                for ar_ in a_rows_:
                    for br_ in b_rows_:
                        _task_i_positions[a_name_], _task_i_positions[b_name_] = ar_[1], br_[1]
                        if not _task_i_order_inversions():
                            max_ordered_ = max(max_ordered_, math.dist(ar_[1], br_[1]))
                _task_i_positions[a_name_], _task_i_positions[b_name_] = old_a_, old_b_
                raise SystemExit('Task I: cannot jointly repair separation/N10: %s / %s sep=%s n10=%s candidates=%d/%d max=%.1f ordered=%.1f' %
                                 (a_name_, b_name_, sep_bad_[:3], n10_bad_[:3],
                                  len(a_rows_), len(b_rows_), max_direct_, max_ordered_))
            _, a_row_, b_row_ = pair_repairs_[0]
            _task_i_positions[a_name_], _task_i_positions[b_name_] = a_row_[1], b_row_[1]
            _task_i_building_ids[a_name_], _task_i_building_ids[b_name_] = a_row_[2], b_row_[2]
            continue
        _, repair_name_, repair_row_ = min(repairs_, key=lambda row_: (row_[0], row_[1]))
        _task_i_positions[repair_name_] = repair_row_[1]
        _task_i_building_ids[repair_name_] = repair_row_[2]
    else:
        raise SystemExit('Task I: separation/N10 repair did not converge')

    if (_task_i_separation_violations() or _task_i_n10_violations() or
            _task_i_n5_violations()):
        raise SystemExit('Task I: separation/N10/N5 violations remain')

    _task_i_group_results = []
    for addr_, names_ in _task_i_same_address_groups:
        distances_ = []
        for i_, a_name_ in enumerate(names_):
            for b_name_ in names_[i_+1:]:
                distances_.append((a_name_, b_name_,
                                   math.dist(_task_i_positions[a_name_],
                                             _task_i_positions[b_name_])))
        _task_i_group_results.append((addr_, distances_))

    _task_i_moves = []
    for sh in shops:
        old_ = (sh['tx'], sh['ty'])
        new_ = _task_i_positions[sh['name']]
        move_ = math.dist(old_, new_)
        sh['x'], sh['y'] = round(new_[0], 1), round(new_[1], 1)
        if move_ > 0.05:
            _task_i_moves.append((sh['name'], move_))

    # タップ領域は最終位置から再導出し、生成物を次ビルドの入力にしない。
    for sh in shops:
        nearest_ = min((math.hypot(sh['x']-other_['x'], sh['y']-other_['y'])
                        for other_ in shops if other_ is not sh), default=44.0)
        sh['padr'] = max(6, min(22, int(nearest_/2.0)-1))

    def _task_i_containing_buildings(point_):
        return [b_ for b_ in _task_i_buildings
                if b_[0]-1 <= point_[0] <= b_[2]+1 and b_[1]-1 <= point_[1] <= b_[3]+1
                and _task_i_poly_inside(b_[4], point_)]

    _task_i_outside_after = []
    for sh in shops:
        point_ = (sh['x'], sh['y'])
        if sh['name'] not in _task_i_open_sites and not _task_i_containing_buildings(point_):
            _task_i_outside_after.append(sh['name'])
        if not _task_i_road_safe(sh, point_):
            raise SystemExit('Task I road/star clearance failed after snap: %s' % sh['name'])
        if _task_i_side(point_) != _task_i_side((sh['tx'], sh['ty'])):
            raise SystemExit('Task I building snap crossed busway: %s' % sh['name'])
    if _task_i_outside_after:
        raise SystemExit('Task I shops still outside buildings: %s' % _task_i_outside_after)

    for upper_name_, lower_name_, expected_sep_ in _task_i_pair_results:
        upper_, lower_ = _task_i_by_name[upper_name_], _task_i_by_name[lower_name_]
        actual_sep_ = math.hypot(upper_['x']-lower_['x'], upper_['y']-lower_['y'])
        if not upper_['y'] < lower_['y'] or actual_sep_ < 8.4 - 1e-9:
            raise SystemExit('Task I same-address pair guard failed: %s / %s' %
                             (upper_name_, lower_name_))

    # 最終67本未満のネットワーク全端点を、接続・canvas外・OSM way実端点の
    # いずれかへ機械分類する。どれにも属さない中空端点は不正。
    _task_i_raw_endpoints = []
    for e in raw.get('elements', []):
        if (e.get('type') != 'way' or not e.get('geometry') or
                not e.get('tags', {}).get('highway')):
            continue
        for q_ in (e['geometry'][0], e['geometry'][-1]):
            gx_, gy_ = project(q_['lat'], q_['lon'])
            _task_i_raw_endpoints.append(wobble(gx_-minx, gy_-miny))
    _task_i_endpoint_quality = {'connected': 0, 'canvas_exit': 0, 'osm_source': 0,
                                'floating_endpoints': 0}
    for i_, road_ in enumerate(roads):
        for point_ in (road_['pts'][0], road_['pts'][-1]):
            if not (0 <= point_[0] <= W and 0 <= point_[1] <= H):
                _task_i_endpoint_quality['canvas_exit'] += 1
                continue
            connected_ = any(
                j_ != i_ and _task_i_road_distance(point_, other_) < 2.0
                for j_, other_ in enumerate(roads)
            )
            if connected_:
                _task_i_endpoint_quality['connected'] += 1
                continue
            source_ = min((math.dist(point_, q_) for q_ in _task_i_raw_endpoints), default=1e9) <= 5.0
            if source_:
                _task_i_endpoint_quality['osm_source'] += 1
            else:
                _task_i_endpoint_quality['floating_endpoints'] += 1
    if _task_i_endpoint_quality['floating_endpoints']:
        raise SystemExit('Task I floating road endpoints: %d' %
                         _task_i_endpoint_quality['floating_endpoints'])

    def _task_i_intersection(a_, b_, c_, d_):
        den_ = ((b_[0]-a_[0])*(d_[1]-c_[1]) -
                (b_[1]-a_[1])*(d_[0]-c_[0]))
        if abs(den_) < 1e-12:
            return None
        t_ = (((c_[0]-a_[0])*(d_[1]-c_[1]) -
               (c_[1]-a_[1])*(d_[0]-c_[0])) / den_)
        u_ = (((c_[0]-a_[0])*(b_[1]-a_[1]) -
               (c_[1]-a_[1])*(b_[0]-a_[0])) / den_)
        if -0.001 <= t_ <= 1.001 and -0.001 <= u_ <= 1.001:
            return (a_[0]+t_*(b_[0]-a_[0]), a_[1]+t_*(b_[1]-a_[1]))
        return None

    _task_i_nodes = []
    for i_, road_ in enumerate(roads):
        for other_ in roads[i_+1:]:
            for a_, b_ in zip(road_['pts'], road_['pts'][1:]):
                for c_, d_ in zip(other_['pts'], other_['pts'][1:]):
                    hit_ = _task_i_intersection(a_, b_, c_, d_)
                    if hit_:
                        _task_i_nodes.append(hit_)
    _task_i_unique_nodes = []
    for point_ in _task_i_nodes:
        if not any(math.dist(point_, other_) < 12 for other_ in _task_i_unique_nodes):
            _task_i_unique_nodes.append(point_)
    _task_i_signal_distances = [
        min((math.dist(signal_, node_) for node_ in _task_i_unique_nodes), default=1e9)
        for signal_ in signals
    ]
    if not all(distance_ <= 20.0 for distance_ in _task_i_signal_distances):
        raise SystemExit('Task I signal intersection guard failed: %s' %
                         [(row_[0], row_[1], round(distance_, 1))
                          for row_, distance_ in zip(_task_i_signal_display_rows,
                                                     _task_i_signal_distances)])

    meta['road_counts'] = dict(sorted(Counter(r['cls'] for r in roads).items()))
    meta['road_quality'] = {
        **_task_i_endpoint_quality,
        'before': _task_i_roads_before,
        'after': len(roads),
        'net_added': len(roads)-_task_i_roads_before,
        'osm_ways_used': len(_task_i_way_ids),
        'connected_existing_fragments': 2,
        'two_point_paths': sum(len(r['pts']) == 2 for r in roads),
    }
    meta['shop_positioning'] = {
        'moved_count': len(_task_i_moves),
        'max_move_m': round(max((row_[1] for row_ in _task_i_moves), default=0.0), 2),
        'moved': [row_[0] for row_ in sorted(_task_i_moves, key=lambda row_: (-row_[1], row_[0]))],
        'outside_after': _task_i_outside_after,
        'north_south_inversions': len(_task_i_order_inversions()),
        'same_address_groups': [
            {'addr': addr_, 'pairs': [[a_, b_, round(d_, 2)] for a_, b_, d_ in rows_]}
            for addr_, rows_ in _task_i_group_results
        ],
    }
    meta['signal_counts'] = {
        'displayed': len(signals), 'osm_one_to_one': len(_task_i_signal_rows),
        'merge_threshold_m': SIGNAL_MERGE_DISTANCE_M,
        'merged_intersection_groups': sum(len(ids_) > 1
                                          for ids_, _ in _task_i_signal_display_rows),
        'merged_signal_nodes': _merged_signal_nodes,
        'removed_manual': 2, 'added_required': 2,
        'at_intersection_20m': sum(d_ <= 20.0 for d_ in _task_i_signal_distances),
        'max_intersection_distance_m': round(max(_task_i_signal_distances), 2),
    }
    print('Task I production: shops moved=%d max=%.1fm roads=%d signals=%d floating=%d' %
          (len(_task_i_moves), meta['shop_positioning']['max_move_m'], len(roads), len(signals),
           meta['road_quality']['floating_endpoints']))

print('zones:', zones)

# 出力の直前だけ公式表記に差し替える (内部の対応表は元の名前で引いているため)
apply_official_fixes(shops, '出力')

# ---------------- 電話・営業時間・定休日 ----------------
# 公式 nakayaman.com の各店ページに書かれているのに、地図側は0件だった。
# 取り込み結果は official_details.json に凍結してあり、ビルドのたびに公式へ取りに行かない
# (更新は tools/v2-build/scrape_official_details.py を手で回す)。
_details_path = P('official_details.json')
if os.path.exists(_details_path):
    with open(_details_path, encoding='utf-8') as f:
        _details = json.load(f).get('shops', {})
    _filled = 0
    _addr_mismatch = []
    for sh in shops:
        got = _details.get(sh['name'])
        if not got:
            continue
        for key in ('tel', 'hours', 'closed'):
            if got.get(key):
                sh[key] = got[key]
        if got.get('addr') and sh.get('addr'):
            a = re.sub(r'[\s　]', '', got['addr'])
            b = re.sub(r'[\s　]', '', sh['addr'])
            if a != b:
                _addr_mismatch.append('%s: 地図=%s / 公式=%s' % (sh['name'], sh['addr'], got['addr']))
        _filled += 1
    print('公式の掲載情報を入れた店: %d / %d' % (_filled, len(shops)))
    print('  電話 %d件 / 営業時間 %d件 / 定休日 %d件'
          % (sum('tel' in s for s in shops), sum('hours' in s for s in shops),
             sum('closed' in s for s in shops)))
    if _addr_mismatch:
        print('  住所が公式と食い違う: %d件' % len(_addr_mismatch))
        for row in _addr_mismatch:
            print('    ' + row)
else:
    print('official_details.json が無いので電話・営業時間は入れない')

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

# ---------------- 自前フォントの詰め直し ----------------
# 店名を1つ足しただけでその字がフォントに無い、という取りこぼしを防ぐため、
# HTML を書いた直後に必ず作り直す (fonttools が無い環境では黙って飛ばす)。
if not ARGS.preview:
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import make_fonts
        print('自前フォント:')
        make_fonts.build(list(OUT_HTMLS))
    except Exception as _e:                      # フォントが作れなくても地図は出る
        print('  フォントの作り直しに失敗 (端末のフォントで表示される):', _e)

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
