# Task AQ 実装結果

対象の手編集: `tools/v2-build/template.html`

## 現在地

Task AP-2 の配置ロジックは修正し、`python tools/v2-build/build_mapdata.py` による再生成まで実施した。
ただし、この Codex セッションではブラウザプロセスの IPC 作成が Windows サンドボックスに拒否されたため、ブラウザ版 `gate.py` の N26 / N37 / N38 / N41 / N42 / N48 は未確認。`--no-browser` の表示は合否根拠にしていない。

## 修正内容

### 1. 引き出し線の距離と描画を分離

- 配置合否用の線分は、N37 / N38 が検査するものと同じ `★中心 → ラベル中心` に戻した。
- 上限は通常 **90px**、こどもの声 **130px** のまま。変更していない。
- SVG で実際に描く線は `★の縁 → ラベル矩形の最寄り辺` のまま維持した。表示線を不必要に長くしない。
- 他店の★から6.5px以内を通る候補、他ラベルを横切る候補、上限を超える候補は配置候補から外す。

### 2. 優先度3が場所を勝ち取る配置へ変更

1. 優先度1（声なし・URLなし）のラベルだけを仮置きする。
2. こどもの声11店（優先度3）を同時探索する。
3. 優先度3の候補と衝突した仮置きラベルは、**優先度1だけ**退けられる。優先度2は退避対象にしない。
4. 優先度3を確定後、優先度2を配置し、退避対象でない優先度1を再配置する。
5. 退けた店名は `document.body.dataset.evictedLabels` と `window.__labelEvictions` に JSON 配列で記録する。

既存の候補位置に「近距離の引き出し線扱い」を追加した。距離上限・店座標・道路座標・信号座標は変更していない。

## 退けた店名

**実ブラウザ上の確定リスト: 未取得。0件とは判定していない。**

ブラウザ実行時にはページ自身が `data-evicted-labels` に実際の店名だけを列挙する。退避対象になり得る優先度1は次の6店だが、これは候補集合であり、実際に退けた店の確定値ではない。

- 東北電力研究開発センター
- 中山郵便局
- 中山ドライブスクール
- 中山鳥瀧不動尊（目の神様）
- 商店街モニュメント
- たきみち公園

ブラウザ版 gate が動く環境で、`document.body.dataset.evictedLabels` の値をこの節へ転記して確定する必要がある。犠牲を隠して0件扱いにはしていない。

## 検証

| やったこと | 物理証拠 | 完了Layer | 残・次手 |
|---|---|---|---|
| テンプレート修正と生成HTML更新 | `tools/v2-build/template.html` / `index.html` / `v2.html` | Layer 2 | ブラウザ採点 |
| builder再生成 | `python tools/v2-build/build_mapdata.py` / exit 0 / shops=60 / roads=66 / signals=13 | Layer 3 | なし |
| 連続生成の再現性 | `index.html` / `v2.html` SHA-256 `CD74CD82B7EB2D7CE83E40DC8D1E29E57FAA795FDB599D232A1EEB83504B750F`、連続生成で一致 | Layer 3 | なし |
| 生成JavaScript構文 | `index.html` / `v2.html` とも scripts=1、`new Function` parse OK | Layer 3 | 実ブラウザ動作 |
| 線長・優先度・退避記録の静的invariant | 90/130維持、中心距離判定、最寄り辺描画、優先度1だけ退避、退避名JSON記録を各 `True` で確認 | Layer 3 | 実測値 |
| 保護ファイル | `git diff --exit-code -- tools/v2-build/gate.py preview.html tools/v2-build/preview.template.html tools/v2-build/mapdata.json` / exit 0 | Layer 3 | なし |
| 座標資産 | `tools/v2-build/mapdata.json` SHA-256 `3447DAF4A45CD66DF785E5F01096323E6DE160B642A46AC562D387FB19CC9C74`（Task AP時点と一致） | Layer 3 | なし |
| 差分健全性 | `git diff --check` / exit 0 | Layer 3 | なし |
| ブラウザ版 gate | `.tmp-runtime/task-aq-gate-browser.stderr.txt`: Playwright子プロセス作成 `PermissionError [WinError 5]`。in-app Browser一覧0件。Edge headlessも IPC `アクセスが拒否されました` | 未到達 | ブラウザ実行可能な reviewer が N26/N37/N38/N41/N42/N48 と退避名を確認 |

## 保護SHA

- `tools/v2-build/gate.py`: `2D9FD3C96BA682F462F936ECF66FFD5FAADB95EA5454FBD9ADEAAD23B4CFEEAE`
- `preview.html`: `87BAF924A5CA7F63975D2293CD00ABDD91432F52FCD6215792612A302C15DA44`
- `tools/v2-build/preview.template.html`: `ABAA1349015B8022AFD1FEA65FE8B237E1B68E2D2E041AF2C94553409E369EBC`

## Done Definition 判定

| 条件 | 状態 |
|---|---|
| N26 = 0 | ブラウザ未確認 |
| N37 = 0 / N38 = 0 | ブラウザ未確認 |
| N41 / N42 / N48 非回帰 | 対象ロジックは未変更、ブラウザ未確認 |
| ★とタップを全60店で維持 | 生成データ60店・対象コード未変更、ブラウザ未確認 |
| ラベル可視40件以上 | ブラウザ未確認 |
| 退けた店名の列挙 | 実装は動的記録済み、実ブラウザ確定値は未取得 |

この結果は Layer 3 のローカル生成・静的検証までを保証する。ブラウザ版 `gate.py` の PASS は主張しない。
