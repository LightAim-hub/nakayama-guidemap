# -*- coding: utf-8 -*-
"""このマップで実際に使う字だけのフォントを作る。

2026-08-04 の実測: 遅い回線での通信量の 87% が Google Fonts だった。
日本語のWebフォントは字形が細かく分かれていて 87 ファイルを取りに行くため、
表示が出そろうまで時間がかかる。このマップに出る字は作った時点で全部決まっているので、
その字だけを詰めた1ファイルにして自分で持つ。

- 出力: assets/fonts/*.woff2 と、埋め込む用の @font-face (fonts_face.css)
- 元フォント: Yusei Magic / Zen Maru Gothic (どちらも SIL Open Font License 1.1)
  ライセンス全文は assets/fonts/OFL.txt に同梱する。
- 字が足りない時は端末のフォントで出る (display:swap と同じ挙動) ので、
  取りこぼしても文字が消えることはない。それでも見た目が変わるので、
  build_mapdata.py から毎回呼んで作り直す。
"""
import os, re, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_fontsrc')
OUT_DIR = os.path.join(ROOT, 'assets', 'fonts')

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
# 元データは Google Fonts の配布元リポジトリ (フォント本体と OFL.txt が同じ場所にある)。
# css2 API 経由だと字形で分割された woff2 しか取れず、詰め直せない。
GF_RAW = 'https://raw.githubusercontent.com/google/fonts/main/ofl/'

FONTS = [
    # (出力名, 配布元パス, font-family, weight)
    ('yusei-magic-400',     'yuseimagic/YuseiMagic-Regular.ttf',    'Yusei Magic',     '400'),
    ('zen-maru-gothic-400', 'zenmarugothic/ZenMaruGothic-Regular.ttf', 'Zen Maru Gothic', '400'),
    ('zen-maru-gothic-700', 'zenmarugothic/ZenMaruGothic-Bold.ttf',    'Zen Maru Gothic', '700'),
]
LICENSES = ['yuseimagic/OFL.txt', 'zenmarugothic/OFL.txt']

# 本文に出ていなくても、あとから増えうる字は先に入れておく
# (数字・記号・かな全部。漢字だけは実際に使うものに絞る)。
ALWAYS = (
    ''.join(chr(c) for c in range(0x20, 0x7f))
    + ''.join(chr(c) for c in range(0x3041, 0x30ff + 1))
    + '　、。・ー〜！？（）「」『』［］【】…：；／＋−＝％＃＠＊'
    + '０１２３４５６７８９'
    + '↗→←↑↓★☆●○◆■♪℃㎡№'
)


def fetch(url, ua):
    req = urllib.request.Request(url, headers={'User-Agent': ua})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def source_ttf(key, rel):
    """元フォントを取ってきて置いておく (once)。"""
    path = os.path.join(SRC_DIR, key + '.ttf')
    if os.path.exists(path) and os.path.getsize(path) > 100000:
        return path
    os.makedirs(SRC_DIR, exist_ok=True)
    data = fetch(GF_RAW + rel, UA)
    if data[:4] not in (b'\x00\x01\x00\x00', b'OTTO', b'true', b'ttcf'):
        raise RuntimeError('フォントとして読めないものが返ってきた: ' + rel)
    with open(path, 'wb') as f:
        f.write(data)
    return path


def save_licenses():
    """OFL は再配布時の同梱が条件なので、必ず一緒に置く。"""
    os.makedirs(OUT_DIR, exist_ok=True)
    for rel in LICENSES:
        name = rel.split('/')[0].upper() + '-OFL.txt'
        dst = os.path.join(OUT_DIR, name)
        if os.path.exists(dst):
            continue
        with open(dst, 'wb') as f:
            f.write(fetch(GF_RAW + rel, UA))


def used_chars(html_paths):
    chars = set(ALWAYS)
    for p in html_paths:
        with open(p, encoding='utf-8') as f:
            chars |= set(f.read())
    # 制御文字は落とす
    return ''.join(sorted(c for c in chars if ord(c) >= 0x20))


def build(html_paths, quiet=False):
    try:
        from fontTools.subset import main as subset_main  # noqa: F401
        from fontTools import subset as ftsubset
    except ImportError:
        if not quiet:
            print('  fonttools が無いのでフォントの作り直しは飛ばす (pip install fonttools brotli)')
        return None
    os.makedirs(OUT_DIR, exist_ok=True)
    save_licenses()
    text = used_chars(html_paths)
    faces, total = [], 0
    for key, family, css_family, weight in FONTS:
        src = source_ttf(key, family)
        dst = os.path.join(OUT_DIR, key + '.woff2')
        # 縦書き・特殊合字は使っていないので置き換え表は最小限に。
        args = [src, '--text=' + text, '--flavor=woff2', '--layout-features=kern,liga,palt',
                '--output-file=' + dst, '--no-hinting', '--drop-tables+=vhea,vmtx,VORG']
        ftsubset.main(args)
        size = os.path.getsize(dst)
        total += size
        if not quiet:
            print('  %-22s %6.1f KB (元 %5.0f KB)' % (key, size / 1024, os.path.getsize(src) / 1024))
        faces.append(
            "@font-face{font-family:'%s';font-style:normal;font-weight:%s;font-display:swap;"
            "src:url('assets/fonts/%s.woff2') format('woff2');}" % (css_family, weight, key))
    css_path = os.path.join(OUT_DIR, 'fonts_face.css')
    with open(css_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(faces) + '\n')
    if not quiet:
        print('  合計 %.1f KB / 収録した字 %d 種' % (total / 1024, len(text)))
    return {'css': '\n'.join(faces), 'bytes': total, 'chars': len(text)}


if __name__ == '__main__':
    paths = sys.argv[1:] or [os.path.join(ROOT, 'index.html')]
    build(paths)
