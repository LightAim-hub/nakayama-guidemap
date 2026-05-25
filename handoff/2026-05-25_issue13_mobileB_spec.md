# Handoff — Issue #13 スマホUI刷新(案B)

- 日付: 2026-05-25 / 設計: Claude Code (L.A.M.I.A) / 実装: Codex / 検証: L.A.M.I.A (Playwright)
- 対象: `index.html` 単一ファイル。**既存の STORES/URL/スタンプ(naka_stamps_v1)/位置補正/カテゴリフィルタ/季節/バブル の機能を壊さない**。
- 目的: スマホで「探す(リスト)」と「地図を見る」を分離し、1画面の情報過密を解消。地図上の常時装飾を整理。

## レイアウト（上から）
1. header（コンパクト・現状維持）
2. **スタンプ進捗スリムバー**（1行）＋「📖スタンプ帳」（既存を1行に圧縮）
3. **イベント1行バナー** `.event-banner`（地図から剥がす）: 「🎏 {確定イベント} まで あと{n}日」。データは既存ロジック流用（七夕8/6-8・毎月第3土曜の街道市のみ・捏造なし）。
4. **検索＋カテゴリ**: `<input type="search" id="shopSearch" placeholder="お店をさがす（名前で検索）">` ＋ 既存チップ。
5. **地図エリア**（レスポンシブ↓）
6. **店舗リスト** `#shopList`（既存・モバイルでは主役）
7. 注記

## 地図のレスポンシブ挙動（肝）
- **デスクトップ ≥860px**: 地図を**インライン表示**（現状の `.map-wrap` のまま）。季節装飾・声バブルは可視なので従来通り（ただし控えめ）。
- **モバイル <860px**: インライン地図は**非表示**。代わりに「🗺 地図で見る」大ボタン `.open-map-btn`（min-height48px）。タップで**全画面オーバーレイ** `.map-overlay`（`position:fixed; inset:0; z-index:1000; background:var(--bg)`）を開き、その中に地図(`.map-wrap`)＋hit＋popup＋季節装飾＋声バブル＋「✕閉じる」を表示。
  - 実装方針: `.map-wrap` は1つだけ。CSSで「モバイル時は `.map-overlay`(初期 `display:none`) の中に入っているように見せる」ため、**地図ブロックを `.map-overlay` でラップし、デスクトップは `.map-overlay{display:contents/通常表示}`、モバイルは `display:none`→ボタンで `.open` クラス付与時 `display:flex` でフルスクリーン**、とするのが安全。1つの map-wrap を使い回す。
  - オーバーレイ open 時: `body` に `overflow:hidden`（背景スクロールロック）。close は ✕／Esc／背景タップ。
  - 縦長地図(977/1339)は overlay 内で `overflow:auto` 縦スクロール許容（または幅fit）。
  - overlay ヘッダー: 「なかやま地図」＋✕。

## デクラッタ（必須）
- **声バブルの `setInterval` は地図が可視な時だけ稼働**。モバイルは overlay open 時に開始、close 時に `clearInterval`。デスクトップは従来通り。
- **季節装飾**も地図可視時のみ描画（モバイルは overlay 内）。
- これでモバイル初期表示＝「header＋スリムバー＋イベント1行＋検索＋チップ＋地図ボタン＋クリーンなリスト」だけ＝スッキリ。

## 検索ボックス（新規）
- `#shopSearch` 入力で店舗リスト行を `s.name.includes(値)` で絞り込み。**カテゴリチップとAND**（activeCats かつ 検索一致）。
- 既存のフィルタ関数に検索条件を統合（リスト行 display 切替・地図 glow は任意）。空文字で全解除。

## popup座標
- 既存 showPopup は `mapWrap.getBoundingClientRect()` 相対計算なので、map-wrap が overlay 内に入っても原則そのまま動く。**ただし overlay 内スクロール時のズレに注意** → overlay 内 scroll 中に開いている popup があれば閉じる or 再計算。最低限、overlay を開く/閉じる際は popup を閉じる。

## 厳守
- 既存機能（URL42・スタンプ・位置補正・季節・バブル・カテゴリ）回帰なし。
- 横スクロール無し。`map-wrap` 二重生成や STORES.forEach 重複を作らない（grep で1系統維持）。
- テーマ変数流用。JS構文エラーゼロ。

## やらないこと（別Phase）
- 目の神様おまいり/クイズ/店主の一言/営業時間サイン（Issue別）。ピンチズーム（将来）。
