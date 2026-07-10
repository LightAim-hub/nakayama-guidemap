# なかやま商店街 デジタルガイドマップ

公開URL: **https://lightaim-hub.github.io/nakayama-guidemap/**

なかやま商店街（仙台市青葉区）の店舗・施設を、OpenStreetMapと国土地理院の位置情報に基づいて表示するデジタルマップです。カテゴリ絞り込み、店舗検索、店舗紹介、こどもの声、スマートフォン操作に対応しています。

## 構成

| ファイル | 内容 |
|---|---|
| `index.html` | GitHub Pagesの本番入口 |
| `v2.html` | 既存共有URLとの互換用。本番入口と同じ生成物 |
| `tools/v2-build/template.html` | HTML/CSS/JavaScriptの編集元 |
| `tools/v2-build/build_mapdata.py` | 位置データとHTMLの生成スクリプト |
| `tools/v2-build/mapdata.json` | 生成された中間データ |

GitHub Pagesは`main`ブランチのルートを公開します。`index.html`と`v2.html`は生成スクリプトから同時に更新し、内容を分岐させません。

## 生成

```powershell
python tools/v2-build/build_mapdata.py
```

生成後に次の4ファイルが変更対象になります。

- `index.html`
- `v2.html`
- `tools/v2-build/mapdata.json`
- 生成元を変更した場合は`tools/v2-build/template.html`または`build_mapdata.py`

## データと確認モード

- 店舗情報の基準日: 2026年6月12日
- 地図位置: OpenStreetMap実測ノード、国土地理院住所検索、確認済み概算地点
- `?debug=1`: 座標出典と調整位置を表示
- `?edit=1`: 店舗位置のドラッグ調整と座標JSONの書き出し

宮城大学ロゴは使用許可と正式画像の受領後に、`MIYAGI_UNIVERSITY_LOGO_SRC`へ配置パスを設定して表示します。許可待ちの間は画面に表示しません。

詳細な出典と要確認事項は`handoff/v2_data_provenance.md`を参照してください。
