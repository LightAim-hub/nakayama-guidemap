# BT: こどもの声を台帳駆動にする ＋ 訂正9件 ＋ 「いま」を構造化時間で判定する

Issue: <https://github.com/LightAim-hub/nakayama-guidemap/issues/53>
claim: <https://github.com/LightAim-hub/nakayama-guidemap/issues/53#issuecomment-5290084886>
owner_label: `ai:codex` (付与済み) / codex_mode: implement
upstream 設計: このファイル。実装はここだけ読めば足りる。

## 起点

2026-08-14、あみさん（中山商店街振興組合の窓口）から「**声が反映されていない場所がある。再度確認。**」。
こどもの声の一次台帳 xlsx が再送されたので突き合わせたら、**台帳 69行 / 23箇所に対して地図に出ていたのは 26件 / 11店**だった。

原因は「写し漏れ」ではなく**構造**: 声は `verified_shops.json` に手で写した分しか無く、
**xlsx を読む経路がそもそも無い**。だから落ちても誰も気づけない。ここを台帳駆動にする。

## 私（Claude Code）が先に作ったもの — **触らないでそのまま使う**

| ファイル | 中身 |
|---|---|
| `tools/v2-build/voices_master.json` | 台帳 69行 / 23箇所。**本文は1文字も変えない**。`places[].shops` = 出す先の店名、`places[].skip_reason` = 出す先が無い理由 |
| `tools/v2-build/client_corrections.json` | あみさん訂正。`corrections`(9件適用/1件保留) `renames`(花祭壇→花さいだん) `removals`(商店街モニュメント) |
| `tools/v2-build/holidays.json` | 内閣府CSV由来の祝日 35日分 (2026-01-01〜2027-11-23) |
| `tools/v2-build/make_voices_master.py` `make_holidays.py` | 上を作り直すスクリプト。**回す必要は無い** |
| `tools/v2-build/_source/` | 一次ソース (xlsx / 内閣府CSV) |

## 触ってよい / いけない

- **触る**: `tools/v2-build/build_mapdata.py` / `tools/v2-build/template.html` / `tools/v2-build/gate.py` / `tools/v2-build/baseline.json`
- **触らない**: 上の表の6つ / `official_details.json`（公式サイトの写し。訂正は上に重ねる層でやる）/
  `verified_shops.json` の座標 / `lat,lng,tx,ty` / `preview.html` / `preview.template.html` / `diag_*.py` / `lens_*.py`
- `index.html` / `v2.html` は `build_mapdata.py` の生成物。**手で編集しない。ビルドまで必ず実行する。**

---

## 1. `build_mapdata.py` — 声を台帳から作る

### 1-1 声の入口を1本にする

`voices_master.json` を読み、`places[].shops` に挙がった店へ `places[].voices` をそのまま入れる。
**`verified_shops.json` の `voices` は使わない**（`s.get('voices', [])` を台帳由来に差し替える）。二重管理をやめる。

- `ダブルエッグ` は `shops` が2つ (`Double Egg` / `Double Egg4丁目`)。**両方に同じ10行を入れる**
  （台帳が本店と4丁目を区別していない。今の本番も同じ声を両方に出しているので、その挙動を保つ）
- 声の本文は `{"text": "..."}` の形のまま。**トリムも言い換えも句読点の足し引きもしない**

### 1-2 直書きの `voices: []` を撤去する

`build_mapdata.py:446-484` 付近で、たきみち公園 / 中山の坂の上 / 商店街モニュメントを
`'voices': []` で直書きしている。**ここが今回の指摘そのもの**（坂の上とたきみち公園に声が0だった）。
スポットも他の店と同じく台帳から声が入るようにする。

### 1-3 取りこぼしたら止める（これが再発防止の本体）

ビルドの最後に検算し、**1つでも合わなければ `SystemExit` で止める**:

1. `places[].shops` に書いた店名が、出来上がった `shops` に**実在するか**（誤字・改名で静かに消えるのを防ぐ）
2. 台帳の各 place は `shops` か `skip_reason` の**どちらかを必ず持つ**
3. 地図に入った声の行数 = 台帳の行数 − skip の行数（`ダブルエッグ`の二重掲載は数え方を明示してコメントに残す）

停止メッセージは「どの店の何行が行き先を失ったか」まで書く。

### 1-4 訂正を上から重ねる

`client_corrections.json` を読み、

- `corrections[]` で `applied: true` のものだけ `set` の各キー (`hours` / `closed` / `note`) を上書き
  （`applied: false` の**中山歯科は触らない**。文意が2通りに読めるので確認中）
- `hours_struct` / `closed_rules` / `open_now` があれば、その店のレコードにそのまま持たせる（1-6 で画面が使う）
- `renames[]`: `花祭壇` → `花さいだん`。**公式情報の突き合わせが終わったあとに改名する**こと。
  `official_details.json` は `花祭壇` をキーにしているので、先に改名すると詳細が付かなくなる。
  `SPOT_PHOTOS` / `OUTLIERS` / `ADDR_FIX` / `_OSM_CONFIRMED` など**名前で引いている辞書**も確認する
- `removals[]`: `商店街モニュメント` の直書き追加ごと消す

### 1-5 ガードと台帳の更新（回避しない）

モニュメント削除で **60 → 59店**になる。`build_mapdata.py:177-182` の `PRODUCTION_BASELINE` ガードと
`PRODUCTION_MIGRATION_*` の期待値、`baseline.json` を**意図して 59 に更新する**。
ガードを外したり `try` で握りつぶしたりしない。信号 11基・道路 62..78 は変えない。

### 1-6 祝日を GEO に載せる

`holidays.json` の `covers` と `dates` を `meta.holidays` として出力に入れる。
（画面側が「今日は祝日か」を判定するのに使う。表の範囲外なら判定しない＝安全側）

---

## 2. `template.html` — 「いま」を構造化時間で判定する

### なぜやるか（ここを取り違えないこと）

あみさんの指摘は「**『いま』がある店舗とない店舗がある**」。
今の `hoursRangesToday()` は「曜日で違う店」「※注記つき」を**わざと判定しない**（間違って営業中と出す害を避けるため・2026-08-09 ボス判断）。この方針自体は正しい。

問題は、**今回の訂正がほぼ全部『曜日別』の書き方**だということ。
何もしないと「いま」が出る店が**さらに減り、指摘が悪化する**。だから曜日別を読める形にする。

### 2-1 `openNowLabel(s, now)` の判定順

```
1. s.open_now === false            → null（構造化しきれない例外がある店。西原歯科）
2. s.hours_struct がある           → 2-2 の構造化判定
3. どちらも無い                     → 今までの文字列解析（現行コードそのまま・削らない）
```

### 2-2 構造化判定

```
covers = GEO.meta.holidays.covers
今日が covers の外                                   → null（判定しない・安全側）
closed_rules.holidays && 今日が holidays.dates にある  → {text:'本日定休', kind:'closed'}
closed_rules.dates に {day:D} があり 今日の日が D      → {text:'本日定休', kind:'closed'}
closed_rules.annual に {month:M,day:D} が一致          → {text:'本日定休', kind:'closed'}
ranges = hours_struct[今日の曜日]  (0=日 … 6=土)
ranges が undefined                                   → null（その曜日は分からない）
ranges が []                                          → {text:'本日定休', kind:'closed'}
いまの分が ranges のどれかに入る                        → {text:'いま営業中', kind:'open'}
それ以外                                               → {text:'いまは時間外', kind:'closed'}
```

- 値は 0時からの分。`[[540,1200]]` = 9:00〜20:00
- 日またぎ（終了 ≤ 開始）は現行と同じく +1440 して扱う
- **表示に出す文字列 (`hours` / `closed`) は今までどおり掲載どおりのまま**。判定だけ構造化データで行う

### 2-3 声が1店11件になる

なかやまとびのこ公園が 4件 → **11件**になる。`detail-voice` は既に全件描いているので実装変更は要らないが、
**折りたたみを開いた時に箱が中身を切らないこと**（`N59`）と、
一覧・地図の「こどもの声あり」件数表示が実データと合うこと（`lens_fidelity.py` G2）を必ず確認する。

---

## 3. `gate.py` — 検査に焼く

**「検査に無い規則は次のリライトで黙って消える」**。実際に過去2件消えている。今回の指摘は全部項目化する。

| 項目 | 中身 |
|---|---|
| N62 | `voices_master.json` の全行が、地図の声か `skip_reason` のどちらかに必ず現れる（取りこぼし0） |
| N63 | 地図に出ている声の本文が台帳の本文と**完全一致**（言い換え・トリム・記号の足し引きを禁止） |
| N64 | `client_corrections.json` の `applied:true` の値が、**本番の詳細シートの表示**と一致（`renames` の花さいだん表記を含む）。あわせて **`applied:false` の中山歯科が `official_details.json` のまま変わっていない**ことも見る（保留を勝手に適用させない） |
| N65 | `removals` の店が本番に存在しない（店名検索・地図の印・一覧のすべてで0件） |

- N63 は生成物 (`index.html` の `GEO`) と台帳の**文字列比較**でよい。画面まで見るのは N64 に任せる
- N64 は既存の実ブラウザ検査と同じやり方で、詳細シートを開いて `営業時間` / `定休日` / 店名を読む

### 検査を足した時の作法（**必ず守る**）

**「通ること」でなく「直す前の版で FAIL すること」を確認する。**
N57・N58 で2度、集める側のキー一覧に足し忘れて**判定が黙って捨てられ、違反0で通った**事故がある。
`SWEEP_KEYS` のような集約の口に新しいキーを足したか、必ず見ること。

確認手順: `git stash` などで直す前の `mapdata.json` / `index.html` に戻して各項目を当て、
**N62〜N65 がそれぞれ違反>0 で FAIL する**ことを1つずつ見てから、直した版で PASS を出す。

---

## 4. Goal / DOD（これが揃って初めて完了）

```bash
python tools/v2-build/build_mapdata.py    # exit 0
python tools/v2-build/gate.py             # exit 0 / N1〜N65 違反0
python tools/v2-build/lens_fidelity.py    # 声の件数表示と実データが一致
python tools/v2-build/diag_geometry.py    # G1=0 G2=0 G3=0 G5=0 が悪化していない
```

数値の DOD:

- 地図の声 = **63件**（台帳69行 − skip16行 = 53行 ＋ ダブルエッグ10行を4丁目にも二重掲載）
  ※この数がズレたら**まず台帳の数え方を疑い、勝手に台帳を直さない**。合わない理由を報告して止まる
- 声が入る店 = **14店**（`BURB usedclothing` は台帳に載っているが声0行なので数に入らない）。
  うち スポット4件 = 中山山の神公園 / なかやまとびのこ公園 / たきみち公園 / 中山の坂の上。
  **坂の上とたきみち公園に声が入っていること**が今回の指摘の本体
- 中山歯科の `closed` は **「水曜、土曜午後、日曜、祝日」のまま変わっていない**こと
  （`applied:false` の保留分。うっかり適用すると、2通りに読める指示の片方を勝手に選んで出すことになる）
- 店数 = **59**（モニュメント削除後）/ 信号 = 11基
- 「いま」が出る店の数が、**訂正前より減っていない**こと（数えて報告する）
- `花さいだん` が 地図・一覧・検索・詳細のすべてで出る。`花祭壇` は残らない
- `商店街モニュメント` がどこにも出ない

**報告に必ず入れるもの**: 上の数値の実測値、N62〜N65 を壊れた版に当てて FAIL させた証拠、
`git diff --stat`、ビルド後の `index.html` のバイト数。

コミットは Issue #53 を参照して1本にまとめる。push はしてよい（本番は GitHub Pages）。
**submit gate まで到達したら終わってよい**。独立レビューは Claude Code が別で回す。
