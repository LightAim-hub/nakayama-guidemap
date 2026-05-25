# Handoff — なかやま全体ドット絵タイルマップ本体 / Issue #23 v3

- 設計: Claude Code (L.A.M.I.A) / 実装: Codex / 検証: L.A.M.I.A (Playwright・honest visual QA)
- 方針確定: 手描きSVG廃止 → **Kenney Tiny Town(CC0)タイルでなかやま全体をドット絵タイルマップ化**。プレビュー(preview-pixel.html)でstyle方向OK。
- 素材: repo の `tiles_tinytown.png`(192x176・16px・12列11行)。タイル番号(index=row*12+col)主要:
  - 草: 0(plain) 1(草) 2(きらめき草)
  - 土の道: 40,41(横の土)  石畳: 43
  - 木: 4(緑大) 3(橙大) 5(茂み)  ※2タイル木は 4(上)+16(下) / 3+15
  - 建物=屋根(上)+壁(下)の2タイル。屋根: 48(青) 52(赤) / 屋根妻: 63(青) 67(赤)。壁: 84,85(茶+窓/ドア) 88,90(灰+窓/ドア)。74茶ドア,78灰ドア。
  - 井戸 57・看板83・柵80-82・きのこ29

## 作るもの（index.html）
- 地図の土台を **`<canvas id="mapCanvas" class="base">`** にして、map-wrap を満たす(既存%hit座標と整合させるため、canvas論理サイズは viewBox相当=977x1339 でもよいが、タイル整数描画優先で **グリッド COLS×ROWS を決め、CSSで100%表示・image-rendering:pixelated**)。
- **グリッド設計(整合性)**: 各店の (x%,y%) を grid(col=round(x/100*COLS), row=round(y/100*ROWS)) に対応させ、その位置に建物(屋根+壁2タイル)を置く。COLS≈24, ROWS≈33 目安(縦長977:1339比)。
- **道**: 中央縦の商店街通り＋上の通り＋左右の枝を、土タイルで描き、建物がその通り沿いに並ぶように。グリッドなので位置ズレが起きない。
- **草で全面を敷き、所々に木(2タイル)・茂み・きのこ・きらめき**。神社は鳥居が無い素材なので省略可 or 看板/特別タイルで代替(捏造しない・無理に置かない)。**梅田川は水タイルが無いので省略**(無理に変な物を置かない)。
- **建物のバリエーション**: カテゴリで屋根色を変える(例 medical=青屋根/food=赤屋根/life=緑系が無いので青or赤を割当/edu=赤)。壁/ドアも数種をローテーションして単調さ回避。
- **発見演出**: 既存の透明 `.hit`(z上)はタップ用に維持。発見済みは hit の ⭐(既存 .hit.stamped::after) で表現。建物自体の色変えは canvas再描画が要るので任意(できれば発見済セルを少し明るく再描画)。
- **既存機能維持**: popup/検索/カテゴリ/おみせずかん/絵馬/クイズ/季節(season-layerはcanvas上にそのまま重ねてOK)/Esc/スクロールロック。STORESデータ不変。

## 厳守
- 複製禁止(map-wrap/popup/shopList/STORES 各1)。横スクロール無。XSS安全(innerHTML不可・createElementNS/canvas)。JS構文OK。
- canvas はレスポンシブ(width100%・aspect維持)・モバイルでもくっきり(pixelated)。
- **ダサい単色図形を自分で描かない**。必ず tiles_tinytown.png のタイルを drawImage で使う。

## 検証(L.A.M.I.A)
Playwrightで canvas描画/建物が道沿い/47店タップで発見/検索/横スクロール無 を確認＋スクショで「ちゃんとRPG町マップか」を厳しく目視。雑なら作り直す。
