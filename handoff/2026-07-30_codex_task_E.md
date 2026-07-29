# Codex 作業指示 E — ベースマップ実網再構築 + 見やすさ刷新（調査統合済み）

作業repo: `C:\Users\paipa\nakayama-guidemap`（main = 最新。Task A〜D 完了済み）
背景: `handoff/2026-07-30_basemap_plan.md`。本specは5視点UI/UX調査（Google/Apple分解・イラスト地図実例・カートグラフィ定石・密集POI UX・現行実装監査）の統合結果を実装項目化したもの。

## 🚨 絶対条件

1. **`index.html` / `v2.html` は1文字も変更しない**
2. **git 操作（add/commit/push）は一切しない**。編集して終わり。検証とcommitはClaude Code側
3. **変更は `tools/v2-build/`（builder+template）に入れて `python tools/v2-build/build_mapdata.py --preview` で `preview.html` を再生成する方式**。preview.html だけの手編集で終わらせない（再現性が壊れる）
4. `innerHTML` 新規使用禁止（XSS対策で全廃済み）。GEO注入の `</` エスケープパイプラインを壊さない
5. **ネットワーク取得は不要・禁止**。道路の生データは `tools/v2-build/osm_raw2.json`（2.5MB）に全網が既にある（実測: residential 904 / service 515 / footway 578 / tertiary 85 / unclassified 56 / secondary 22 / primary 8 / path 72 / steps 65）。信号は `signals_raw.json`。座標は必ず既存 proj（lat0/lon0/cosf/rot 46.4°）を通し、正は GEO 1本に保つ
6. 手描きの可愛さ（クリーム&ブラウン/Yusei Magic/丸み）は**不可侵**。UIの `--paper #FBF4E2` は変更しない（変えるのは地図矩形の地色のみ）
7. 既存機能の回帰ゼロ: カテゴリフィルタ/検索/お店一覧/詳細シート(写真・スワイプ・グラバー)/lightbox/Esc/`?debug=1`/`?edit=1`

## 実装順序（この順で。途中で止まっても各段が単独で成立するように）

### Step 1 — スタイル即効4点（データ不変・現行62本のままで効く）

1. **描画順2パス化**（現 L457-465 相当）: クラス毎の縁→塗り交互をやめ、**全クラスのcasing一括→全クラスのfill一括**（casing: service→minor→mid→major→spine / fill: 同順）。guide_spine 道路が major/mid ループでも再描画される三重描画を解消（中山幹線1号線が計4パス描かれている）
2. **図地分離**: 地図背景rect（現 L444 相当）を `#F2E7C9` へ。道路fill: major/mid/minor = `#FFFDF4` 統一、spine（バス通り）のみ `#FBE9C4`
3. **casing不透明淡色化**（現 L93-100 相当）: opacity 指定を全廃し、紙色に対する事前合成の不透明色へ: spine/major縁 `#9B7F5C` / mid縁 `#AE9373` / minor縁 `#CEBB9E` / service縁(新設) `#D6C6A8`。casing幅 = fill幅+3（片側1.5m）
4. **幅階層再設定**（SVG単位=m）: spine 30/36・major 22/27・mid 14/18・minor 9/12・service 5/6.5（隣接比1.4-1.6倍の定石値）

### Step 2 — データ再構築（builder側）

5. **全網取り込み**: `osm_raw2.json` から名前選別（CORE_BUS_NAMES等のリスト通し）を廃止し class ベースへ:
   - spine = 中山幹線1号線（バス通り・現行どおり特別扱い）
   - major = primary / secondary
   - mid = tertiary / unclassified（**現行mid45本は再分類**し、通り抜け道だけmidに残す）
   - minor = residential / living_street
   - service = service
   - path = footway / path / steps（点線・tier3のみ表示）
6. **衛生規則（ビルド時前処理）**:
   - 同clsで端点距離<2mのチェーンを1本にマージ（通町中山線4分割・菖蒲沢橋線2分割などの断片を統合）
   - canvas±PAD 内で中途半端に終わる端点は、元way形状に沿って**枠外まで延長**（OSM上の実際の行き止まりはそのまま）。ポリラインのクリップは線分単位で正しく（Cohen–Sutherland相当）
   - どこにも接続しない40m未満の孤立断片は削除か minor 降格
   - **中空に浮く端点ゼロ**が合格条件
7. **信号全数化**: `signals_raw.json` から canvas 内全数を取り込み（現行13箇所が全数か突合）。信号gに `class="signal"` を付与
8. **性能予算**: 無名道路は class×役割（casing/fill）毎に d 連結で `<path>` 統合。道路名 textPath 用の named 道路のみ個別 path 可。道路レイヤの総ノード数 < 150。モバイル初期描画 < 1.5s

### Step 3 — ズーム階層とラベル

9. **3帯tier制**: applyZoom（現 L1313-1314 相当）で `svg.dataset.tier` を設定し CSS display で制御:
   - tier1（zoom 95-140%）= 幹線+mid+minor塗のみ。信号/参道/minor縁/service 非表示
   - tier2（140-265%）= minor縁+参道+信号+道路名
   - tier3（265%+）= service+path+細街路名+全店ラベル
   - ジオメトリ（道路網そのもの）はどの tier でも消さない。出し入れは装飾とラベルだけ
   - stroke幅の準線形補正 `k=(zoom/175)^-0.3` を gRoads に一括適用（拡大時にspineが画面を飲み込むのを防ぐ）
10. **ラベル画面px固定**: 現行 FS=16.5（map単位固定）は初期175%で実表示7.4px＝高齢者に読めない。applyZoom 時に font-size を再計算し実表示: 一般店 11-12px / アンカー店（こどもの声あり等）14-15px / 道路名 10px（色 `#7A5C3B`・textPath沿わせ）。ハロー 7px→4-5px。`|s.ly-s.y|>120` のラベルはshowAll時以外リーダー線ごと抑制。バス通り名は600-900m毎に反復配置
11. **AOI帯（商店街ストリップ）**: `GEO.busway` を stroke-width:120・**不透明** `#F6E0B8`・丸キャップで gRoads の下に1本描画（半透明にしない=自己交差の濃度ムラ防止）。凡例に「このオレンジの通り沿いが商店街」1行
12. **初期ビュー**: zoom 175→240、5丁目密集帯（y≈850）センタリング。初回の1画面で「読める店名が並ぶ商店街」を見せる

### Step 4 — 操作UX

13. **選択破壊の停止**: applyZoom/チップ/検索が呼ぶ hideDetail() を「シートをpeek段（snap比≈0.28、DETAIL_SNAP_RATIOSに追加）に畳む+選択★保持」へ分離。選択★は appendChild 最前面化+scale1.35
14. **ピンチズーム+タップ領域**: #viewport に Pointer Events の2指ピンチ（2指中点を不動点に）+ダブルタップ=+45。2ポインタ検出時のみ preventDefault。**+/−ボタンは絶対に残す**（高齢者のジェスチャ完遂率対策）。★のタップ半径 r=max(s.padr, 24/画面スケール) で動的化+タップ点から画面24px以内の最近傍★ヒット（複数候補は既存chooserへ）
15. **コンパスHUD化**: SVG内埋め込み（現 L552-559 相当）を廃止し、`position:fixed` 右上（44pxタップ領域・.zoomctl と同様式）へ。**回転符号は proj で同経度2点を投影して北方向ベクトルを実測してから固定**（思い込みで45°系を置かない）。針の北先端 `#C97B3D`

## 今回やらないこと（提案もしない）

現在地GPSボタン（設計確定済みだが実機E2Eが必要なため次回）/ 建物フットプリント / 横断歩道ゼブラ / ランドマーク絵アイコン / Googleマップリンク / コースチップ / バス停レイヤ / MapLibre乗換（不採用確定）/ 北上向き回転復帰（不採用確定）/ 全61ラベル常時表示（不採用確定）/ ランタイムSVGフィルタ（性能で不採用確定）

## 完了報告に必ず含めるもの（実測値・推測禁止）

1. `python tools/v2-build/build_mapdata.py --preview` exit 0・連続2回の生成一致
2. 道路本数の前後: 62本(切れ端31) → 新clsごとの本数と、**中空に浮く端点が0件**であることの機械検査結果
3. 信号: signals_raw.json 突合の結果（canvas内全数 = 表示数）
4. 道路レイヤのSVGノード数（<150）
5. tier1/2/3 の切替が dataset.tier で効いていること（各tierで表示される要素群）
6. 初期表示のラベル実表示px（store/道路名）と、zoom240・y≈850センタリングの確認
7. ピンチ/ダブルタップ/+−/選択保持/コンパス方位実測値
8. `git diff --stat -- index.html v2.html` が空
9. 既存回帰: 検索/一覧61/詳細シート/写真lightbox/Esc が壊れていないこと（手元で最低限の確認。フルE2EはClaude Code側で実施）
