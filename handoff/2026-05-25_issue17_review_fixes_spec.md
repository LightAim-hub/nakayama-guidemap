# Handoff — Issue #17 レビュー指摘修正（バグ4＋使いにくさ2）

- 日付: 2026-05-25 / 設計: Claude Code (L.A.M.I.A・実機再現確認済) / 実装: Codex / 検証: L.A.M.I.A (Playwright)
- 対象: `index.html` 単一。**既存全機能(案B overlay/検索/スタンプnaka_stamps_v1/絵馬naka_ema/クイズnaka_quiz/季節/バブル/URL42/位置補正/カテゴリ)を壊さない・複製禁止**。

## 🔴 修正1: Escでpopupが閉じない（実機確認: pin後Esc→閉じない）
keydownのEscハンドラを優先順位付きに統一:
```
if(Escape){
  if(feature-modal表示中) closeFeatureModal();
  else if(stampbook表示中) closeStampbook();
  else if(mapOverlay open) closeMapOverlay();
  else if(pinned) closePopup(); pinned=null;
}
```
（popup閉じが抜けていたので追加）

## 🔴 修正2: スタンプ帳/featureモーダルの背景スクロール非ロック＋Esc不可（実機確認: body overflow=visible, Escで閉じない）
- 共通 `lockScroll()`(document.body.style.overflow='hidden') / `unlockScroll()`(復帰) を作り、**スタンプ帳・おまいり/クイズ feature-modal・地図オーバーレイ** の開閉で必ず呼ぶ（複数同時openを考慮し、開いているモーダル数のカウント or 「全部閉じたら解除」）。
- Escハンドラ（修正1）に stampbook を含める。stampbook も ✕/背景タップで閉じられること。

## 🔴 修正3: 検索0件で真っ白（実機確認: 0行・メッセージ無し）
- 検索/フィルタ適用後、可視 `.srow` が0件なら `#shopList` に「🔍 お店が見つかりません」行(`.no-result`)を表示。1件以上で消す。

## 🔴 修正4: 検索が大小文字/全半角を区別（実機確認: KAYA=1, kaya=0）
- 比較を正規化: `norm(s.name).includes(norm(query))`。`norm`= `toLowerCase()` ＋ 全角英数→半角 ＋ カタカナ→ひらがな（最低でも toLowerCase は必須）。
- カテゴリチップとのAND条件は維持。

## 🟠 修正5: PCでhover popupのリンク/スタンプが押せない（ピン→吹き出し移動の隙間で消える）
- `popup` に `mouseenter`(維持)/`mouseleave`(非pin時hidePopup) を追加。
- hit の `mouseleave` は即hideせず、短い猶予(約80-120ms)後に「hitもpopupもhoverされていない & 非pin」なら hide。
- pin(クリック)時の挙動は不変。タッチ端末(`hover:none`)では従来通りクリックで開く。

## 🟠 修正6: Tabで47透明hit踏破地獄＋同一店二重Tab
- 地図hit生成時に `tabindex="-1"` を付与（`aria-label`は残す・click/hoverは維持）。Tabフローは「チップ→検索→リスト/カード」中心に。
- 店舗リストの `<a>`(URL有)は従来通りTab可。

## 厳守
- 既存複製なし（`STORES.forEach`/`map-wrap`/`popup`/`shopList`/`const STORES` 各1系統・grep確認）。STORES本体不変。
- 横スクロール無し。XSS安全(絵馬escapeHtml)維持。JS構文エラーゼロ。
- 全モーダル(popup/stampbook/feature/overlay)が Esc・✕・背景タップで閉じ、閉じたら scroll lock 解除されること。
