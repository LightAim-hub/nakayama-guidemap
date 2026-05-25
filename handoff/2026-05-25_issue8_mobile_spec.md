# Handoff — Issue #8 スマホ最適化（店舗リスト併設＋タップ強化）

- 日付: 2026-05-25 / 発行: Claude Code (L.A.M.I.A・設計/目) / 実装: Codex（手）
- 対象: `index.html` 単一ファイル。**STORES の name/cat/url/x/y/voices は変更しない**（単一ソースとして再利用）。
- 検証: 実装後 L.A.M.I.A が Playwright 実機(360/390/430px)でスクショ確認。

## 測定済みの問題（出典＝実機計測）
- `.hit` 高さ ≈ 5.8px（全47店）→ 指タップ困難
- 中央密集列の隣接ギャップ 1.3〜3px
- popup 幅212px=画面59%、top が負（上にはみ出し）

---

## A. 店舗リスト併設（最重要）
`.map-wrap` と `<p class="note">` の**間**に新セクションを追加。STORES から JS で生成（DOMContentLoaded 時、既存の STORES forEach の近くで）。

### HTML（雛形・JSで `#shopList` を埋める）
```html
<section class="shoplist" aria-label="店舗リスト">
  <h2 class="sl-title">🔍 お店をさがす</h2>
  <p class="sl-hint">上のカテゴリボタンで絞り込めます。タップで公式ページへ。</p>
  <div id="shopList"></div>
</section>
```

### 各行（JS生成）
- `url !== "#"` の店: `<a class="srow c-<cat>" href="<url>" target="_blank" rel="noopener">`
- `url === "#"` の店: `<div class="srow c-<cat> disabled" role="listitem">`
- 行内: `<span class="cdot"></span><span class="sname">店名</span><span class="sgo">{url有→ '→' / 無→ '準備中'}</span>`
- `data-cat="<cat>"` を行に付与（フィルタ用）。
- 並び順は STORES 配列順のまま（グルーピング不要・cdot 色で種別表現）。

### CSS（既存テーマ変数を流用）
- `.shoplist{max-width:720px;margin:4px auto 8px;padding:0 14px}`
- `.sl-title{font-size:clamp(15px,4vw,18px);color:#6b5036;margin:10px 0 2px;text-align:center}`
- `.sl-hint{font-size:clamp(10px,2.8vw,12px);color:#9a8763;text-align:center;margin:0 0 8px}`
- `.srow{display:flex;align-items:center;gap:10px;min-height:48px;padding:8px 12px;border:1.5px solid var(--line);border-radius:12px;background:var(--paper);margin-bottom:7px;text-decoration:none;color:var(--ink);font-size:clamp(13px,3.6vw,15px);font-weight:600;transition:transform .08s,background .15s}`
- `.srow:active{transform:scale(.99);background:#f3e7cc}`
- `.srow .cdot{width:13px;height:13px;border-radius:50%;flex:0 0 auto}`
- カテゴリ色: `.srow.c-medical .cdot{background:var(--c-medical)}` 他3カテゴリも（life/food/edu）同様。
- `.srow .sname{flex:1 1 auto;line-height:1.35}`
- `.srow .sgo{flex:0 0 auto;font-weight:700;color:var(--c-food)}` ※色は各カテゴリ色でも可。
- `.srow.disabled{pointer-events:none;opacity:.6}` `.srow.disabled .sgo{color:#a59576;font-size:12px;font-weight:600}`

### フィルタ連動（重要）
既存の `#filters` クリックハンドラを拡張：チップ toggle 後に「押されているカテゴリ集合 activeCats」を算出し、
- 地図グロー = 現状維持
- リスト: 各 `.srow` を `activeCats.size===0 || activeCats.has(row.dataset.cat)` で `display`（''/'none'）切替。

## B. 地図タップ領域の拡大
- `.hit{height:2.2cqw}` → **`height:3cqw`**
- `.hit.compact{height:1.7cqw}` → **`height:2.4cqw`**
- width は据置。これで中央行ピッチをほぼ埋める（隣接重なりは許容範囲）。

## C. ポップアップを画面内に
`showPopup` 内、`popup.style.top` 設定の直後にクランプを追加：
- 上方向に出すと map-wrap 上端より上（top<8px相当）に出る場合は `popup.classList.add('below')` にフォールバック（下に出す）。
- 既存の `popup.classList.toggle('below', s.y < 16)` を、s.y<16 もしくは上方向で見切れる場合に below とする条件へ拡張。

## やらないこと
- STORES データ本体の変更、座標変更、デザイン全面刷新、地図画像差し替え。
- ズーム/パン機能の新規実装（今回スコープ外）。
