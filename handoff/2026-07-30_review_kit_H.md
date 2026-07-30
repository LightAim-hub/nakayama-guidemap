# Task H レビューキット（Codex完了と同時に発火・2026-07-30 準備）

対象: 本番 `index.html` / `v2.html`（+ builder `tools/v2-build/build_mapdata.py`, `template.html`）
仕様: `handoff/2026-07-30_codex_task_H.md`
基準SHA（Codex着手前の本番）: `16384CD82C346947FB7D59F5F74662657552E0F56EE24BD41A04D103FAEF3D53` / 92,454 bytes
基準コミット: `a84af22`

## 使う資産（棚から降ろす分）

| 資産 | 種別 | 何に使うか |
|---|---|---|
| `superpowers:verification-before-completion` | skill | 「PASSと言う前にそのコマンドを今このターンで走らせたか」の門。証拠なし完了宣言を止める |
| `superpowers:requesting-code-review` | skill | 独立reviewerへの投げ方（session履歴を渡さず、要件とSHA範囲だけ渡す） |
| `superpowers:receiving-code-review` | skill | reviewer指摘の採否判断（Critical即修正 / 誤指摘は根拠つきで押し返す） |
| `multi-lens` | skill | 単票合格の禁止。下の Lens A/B/C/D を独立に通す |
| `four-column-ledger` | skill | 最終報告の型（やったこと / 物理証拠 / 完了Layer / 残） |
| `asset-dod-review` | skill | 「ファイルが変わった ≠ 直った」。実画面を物理Openして目視するまで完成と言わない |
| `code-reviewer` | subagent | Lens A（境界監査）— 独立視点。同一threadの自己レビューは無効 |
| `feature-dev:code-reviewer` | subagent | Lens C（回帰・性能）— 別実装の視点でクロス |
| `architect` | subagent | Lens D（ラベルソルバの設計妥当性・2^n爆発の有無） |
| `verify_H.py` | 自作計測器 | A〜F データ再測（下記） |
| `verify_H_browser.py` | 自作計測器 | ★60 / ラベルbbox交差 / ソルバ実行時間 / 既存回帰 |
| `/code-review ultra` | ボス起動のみ | 本番pushの前に更に厚くしたい時。私からは起動不可・課金あり |

計測器の場所:
```
C:\Users\paipa\AppData\Local\Temp\claude\C--Users-paipa\912049d9-a992-4410-bd28-a7c16c317bf6\scratchpad\verify_H.py
C:\Users\paipa\AppData\Local\Temp\claude\C--Users-paipa\912049d9-a992-4410-bd28-a7c16c317bf6\scratchpad\verify_H_browser.py
```

## ベースライン（Codex着手前の本番・実測済み 2026-07-30 09:2x）

データ側:
```
shops 60 / roads 62 / signals 13 / zones 1 / parks 4
A(真座標から20m以上ズレ) = 41/60
B(バス通りの東西の食い違い) = 0
C(南北の並び順の逆転ペア)  = 42組
D(信号との南北関係が逆)    = 9
E(表示上15m未満の★ペア)   = 0
F(公園ポリゴンとの内外)    = 0
```
ブラウザ側:
```
★可視 60/60 / 可視ラベル 62 / ラベルbbox交差 1件(中杜建設×ん daccha)
layoutLabels 2.4ms / 最大グループ 3 (=2^3) / グループ数 36
一覧 60件 / 検索「公園」3件 / 詳細60枚 / Esc close OK / 声バッジ 11 / JSエラー 0
```

## 合格条件（全Lens全員一致まで push しない）

### Lens A — 境界監査（`code-reviewer` subagent）

preview.html 側の成果が1つでも漏れていたら FAIL。

- [ ] `git diff --stat a84af22..HEAD` の変更ファイルが `index.html` / `v2.html` / `tools/v2-build/*` に限られる
- [ ] `git diff a84af22..HEAD -- preview.html tools/v2-build/preview.template.html` が **空**
- [ ] 店数 60（「中山の坂の上」が増えていない）
- [ ] 道路 62本・信号 13箇所（増減なし）
- [ ] 写真ブロック（`detail-gallery` / `assets/photos/`）が index.html に**入っていない**
- [ ] 「公式ページあり」表記が**変わっていない**
- [ ] tier / ピンチズーム / コンパスHUD / AOI帯 / 初期zoom変更が**入っていない**
- [ ] `innerHTML` 新規使用 0 / GEO注入の `</` エスケープ維持
- [ ] 配色・道路幅・casing の定義が変わっていない

### Lens B — 位置関係の正しさ（私 + `verify_H.py`）

- [ ] A=0 / B=0 / C=0 / D=0 / E=0 / F=0
- [ ] `GEO.zones` が空配列
- [ ] あみさん指摘3点:
  - たけむらや（西）⇔ ウエルシア（東）が 25m前後の斜向かい
  - 柏屋（西）⇔ 河村内科外科クリニック（東）が真向かい
  - BAKERY&BAKE EndRoll が cake NAO より上
- [ ] 指摘区間11店の南北順が真座標順と一致
- [ ] 同一住所ペア5組の±分離が維持（重なり回避）
- [ ] Googleマップ照合（済・下記「照合済み事実」）と矛盾しない

### Lens C — 回帰と性能（`feature-dev:code-reviewer` subagent + `verify_H_browser.py`）

- [ ] ★可視 = 60（1つも消えていない）
- [ ] ラベルbbox交差 = 0（ベースライン1件より悪化させない）
- [ ] `layoutLabels` 実行時間 < 50ms・最大グループ < 12（2^n爆発なし）
- [ ] JSエラー 0
- [ ] 一覧60件 / 検索「公園」3件 / 詳細60枚 / Esc / 声バッジ11
- [ ] `?debug=1` / `?edit=1` が動く
- [ ] 連続2回ビルドでSHA一致（再現性）

### Lens D — 「ボスの目に何が映るか」（`architect` subagent + 私の目視 + `verify_H_corridor.py`）

データが合っていても**画面で判別できなければ直っていない**。前回ここを飛ばして指摘を受けた。

- [ ] 実画面スクショで、柏屋とウエルシア/河村が**通りを挟んで向かい合って見える**
- [ ] バス通りの描画帯に店が埋まって判別不能になっていない（下記「実測済みの障害」参照）
- [ ] ラベルが★から離れた店に引き出し線が出ている
- [ ] 密集帯が「潰れた団子」になっていない

#### 実測済みの障害 — バス通りの描画幅（2026-07-30 09:3x 実測）

`verify_H_corridor.py` で計測した確定事実:

| 項目 | 実測値 |
|---|---|
| バス通りの塗り幅（`road-main-f`） | **34m**（片側17m） |
| バス通りの縁取り幅（`road-main-c`） | 48m（片側24m） |
| 指摘区間11店のバス通り中心からの距離 | **6.5〜10.9m**（早坂組 21.7m のみ例外） |
| → 帯の下に埋まる店 | **11店中10店** |

OSM の実タグ: 中山幹線1号線 = `highway=tertiary` / `lanes=2` / width指定なし。2車線＋歩道の実幅は概ね12〜14m。1px≒1m の本マップで34mは**実幅の2.5倍**。

つまり Task H が座標を完璧に直しても、**店は道路の絵の下に入り「向かい合っている」ことが画面で見えない**。これは描画の問題で座標の問題ではないので Task H の境界外（spec で道路幅の変更を禁止している）。

→ Task H 完了後に、実測値を添えてボスへ1問出す:「バス通りを実幅(約13m)に細めれば向かい合いが見えます。1行の変更です。やりますか」
→ ボスの原発話「ここの道路との位置が近すぎるとか」は**この件を指している可能性が高い**ので、H の報告と同時に必ず出す。伏せない。

## Googleマップ照合済み事実（2026-07-30 09:2x 実画面20zで確認）

真座標が正しいことの外部裏付け。Lens B の答え合わせに使う。

| Googleマップ上の事実 | 真座標 | 判定 |
|---|---|---|
| 柏屋（西）の真向かいに河村（東）・通りを挟む | 柏屋 ty962.9 / 河村 ty962.3 | 一致 |
| たけむらや⇔ウエルシアは斜向かい・約23m | 25m | 一致 |
| たけむらやはフラワー中山より南 約77m | 70m | 一致 |
| 柏屋はフラワー中山より南 | 23m | 一致 |

住所の裏付け: バス通りが4丁目/5丁目の境界。南下すると東側は 5-19 → 5-11 → 5-7 → 5-6 → 5-2 → 5-1 と番地が減る。指摘区間11店は全て `osm:exact` / `gsi_addr` で、`approx`（推測座標）は Double Egg4丁目 と 商店街モニュメント の2件のみ＝**指摘区間に推測座標なし**。

※ Googleマップは**検証にのみ**使用。座標を焼き込まない（Google Maps Platform 規約 3.2.3 / 3.2.4）。

## 実行順（Codex完了通知が来たら上から）

1. `git diff --stat a84af22..HEAD` と `git diff --stat -- preview.html` で境界を先に確認（境界違反なら即差し戻し・以降不要）
2. `python tools/v2-build/build_mapdata.py`（--preview なし）連続2回・SHA一致
3. `python verify_H.py` → A〜F と あみさん3点
4. ローカルサーバ起動 → `python verify_H_browser.py` → ★/ラベル/性能/回帰
5. Lens A / C / D の subagent を**並列**で投げる（session履歴を渡さず、本ファイルの該当Lensと SHA範囲だけ渡す）
6. 全Lens一致で PASS → 4列台帳で報告 → push。1つでも FAIL → Codex へ差し戻し（本ファイルに実測値を追記）

## Codex完了後に私が当てるパッチ3件（当て先を実測で確定・2026-07-30 12:0x）

### P1. ★の縮みすぎに下限を入れる（Codexの実装が spec 違反寄り）

Codex の `template.html`:
```js
function starSize(s){
  const base = s.name.indexOf('公園')>=0 || s.cat==='place' ? 1.15 : 1;
  const noOverlap = (nearestStarDistance(s) - 1) / 20;
  return Math.max(.12, Math.min(base, noOverlap));   // ← 下限 .12 が問題
}
```
重なりを「縮小」だけで解決していて、変位（spec が許した8m以内の微小変位）を使っていない。実測:
```
★の実サイズ 最小 1.1px / 中央 8.7px / 5px未満 8件 / 3px未満 4件
  1.1px 佐藤次夫税理士事務所 / 1.1px おたからや / 2.0px ダイニングバー 祭 / 2.0px ん daccha とこや
  3.5px 中山不動産 / 3.5px 中杜建設 / 4.5px 認定こども園 TOBINOKO / 4.5px 商店街モニュメント
```
「★60件全表示」は数だけならPASSしてしまう。**下限 = 画面6px** に。デフォルト倍率 0.4487px/m・★の基準幅20単位なので `6/0.4487/20 = 0.669` → 下限 `.67`。残る重なりは南北順と東西を保った8m以内の微小変位で開ける。

### P2. 道路幅を実幅へ（`template.html` の描画4行）

現行 → 変更後（SVG単位=m。縁は現行の比率を維持）

| クラス | 現行 縁/塗 | 変更後 縁/塗 | 実幅の根拠 | 塗りの画面px |
|---|---|---|---|---|
| main（バス通り） | 48 / **34** | 18 / **13** | OSM `tertiary` `lanes=2` ＋歩道 = 12〜14m | 15.3 → **5.8px** |
| major | 38 / 27 | 17 / 12 | primary/secondary 2車線 | 12.1 → 5.4px |
| mid | 21 / 13.5 | 12.5 / 9 | tertiary/unclassified 2車線 | 6.1 → 4.0px |
| minor | 9 / 5.5 | 7 / 5 | residential | 2.5 → 2.2px |
| sando | 3 | 3（変更なし） | 参道・歩道 | |

効果: 柏屋（中心から-10.9m）と河村（+9.4m）が帯（±6.5m）の外に出て、**通りを挟んだ向かい合いが読める**。
限界（正直に）: デフォルトの全街ビューでは 20m = 9px なので、細めても分解しきれない。効くのは拡大時。全街ビューで読ませるにはズーム段（要因3）が必要。

### P3. Double Egg4丁目 の座標を実測へ（`build_mapdata.py`）

現行は**手置きの概算**。`build_mapdata.py` L584-613 が `_x4 = バス通り中心 - 75m, _y4 = 5丁目店 + 8m` と置き、逆変換して `src='approx'` にしている。コメントにも「住所非公開のため要現地確認」とある。

住所が判明したので概算ブロックを削除し、実座標に差し替える。

- 住所 = **仙台市青葉区中山4丁目6-36**（イートイン専門店 / 5丁目19-5 はテイクアウト専門の別店舗）
  - 出典: 公式 `w-egg.jp` / Yahoo!マップ「オムライス食堂 Double Egg 4丁目店」
- 国土地理院 住所検索API で号レベル一致 `宮城県仙台市青葉区中山四丁目６番３６号` → **lat 38.291851 / lng 140.842712**
- 変更: L114 の override を `('gsi_addr', 38.291851, 140.842712)` に / L584-613 の概算ブロックを削除 / `addr` に住所を入れる

結果: tx,ty = 492.4,767.6 → **566.3,899.6（151.2m の修正）**。バス通り中心から -75.9m → -5.5m。
近隣: 遊季ガーデン 28.8m / 中山鍼灸接骨院 29.5m / フラワー中山 42.8m。Googleマップ20zの見た目（フラワー中山の北西・西側）と一致。

## 差し戻し時のテンプレ

```
Task H 差し戻し（Lens X FAIL）
実測: <検査名> = <実測値>（合格条件 = 0）
該当: <店名 / ファイル:行>
原因の当たり: <仮説>
やること: <1行>
境界は Task H spec のまま。preview.html には触らない。
```
