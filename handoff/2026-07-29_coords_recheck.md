# 同一座標ペア10店 座標再確認記録（2026-07-29）

対象生成物: `preview.html`（`python tools/v2-build/build_mapdata.py --preview` で再生成）。同一住所内の個別店舗ピンを一次ソースで確定できないため、共有中心を投影座標で上側 `(-6m, -11m)`、下側 `(+6m, +11m)` に分離した。画面上は `y` が小さい店を「上」とする。

| 店 | 決定 lat/lng・上下 | 根拠 | `src` と理由 | 振興組合／あみさんへの確認事項 |
|---|---|---|---|---|
| BAKERY&BAKE EndRoll | `38.2895301, 140.8461445`・上 | [nakayaman.com掲載](https://www.nakayaman.com/post/bakery-bake-endroll)の中山1-11-5と、あみさんの「cake NAOより上」指摘 | `approx`。同一住所内の個別ピンを確定できず、共有中心から分離したため | EndRollとcake NAOの建物内／敷地内の正確な店舗位置 |
| cake NAO | `38.2894719, 140.8464215`・下 | [nakayaman.com掲載](https://www.nakayaman.com/post/cafe-nao)の中山1-11-5と、あみさんの上下指摘 | `approx`。同一住所内の個別ピンを確定できず、共有中心から分離したため | 同上 |
| 佐藤次夫税理士事務所 | `38.2928111, 140.8414905`・上 | [nakayaman.com掲載](https://www.nakayaman.com/post/%E4%BD%90%E8%97%A4%E7%B4%80%E5%A4%AB%E7%A8%8E%E7%90%86%E5%A3%AB%E4%BA%8B%E5%8B%99%E6%89%80)の中山5-19-5と[紙マップ](../map.png)の描画順 | `approx`。同一住所内の個別ピンを確定できず、紙マップ順に共有中心から分離したため | 税理士事務所とDouble Egg5丁目の正確な区画位置 |
| Double Egg5丁目 | `38.2927529, 140.8417675`・下 | [nakayaman.com掲載](https://www.nakayaman.com/post/double-egg)の中山5-19-5と[紙マップ](../map.png)の描画順 | `approx`。同一住所内の個別ピンを確定できず、紙マップ順に共有中心から分離したため | 同上 |
| サトー商会 | `38.2893241, 140.8504015`・上 | [nakayaman.com掲載](https://www.nakayaman.com/post/sato-aramaki)の荒巻本沢1-17-4、元座標 `38.289295, 140.850540`、[紙マップ](../map.png)の描画順 | `approx`。振興組合掲載住所の共有中心から紙マップ順に分離したため | 自社サイト `satoh-web.co.jp` は1-17-14表記。振興組合掲載の1-17-4とどちらを正とするか |
| みなとや | `38.2892659, 140.8506785`・下 | [nakayaman.com掲載](https://www.nakayaman.com/post/minataya)の荒巻本沢1-17-4、元座標 `38.289295, 140.850540`、[紙マップ](../map.png)の描画順 | `approx`。振興組合掲載住所の共有中心から紙マップ順に分離したため | サトー商会と同じ共有住所でよいか、正確な区画位置 |
| デイサービス はるの風 | `38.2921621, 140.8423905`・上 | [nakayaman.com掲載](https://www.nakayaman.com/post/%E3%83%87%E3%82%A4%E3%82%B5%E3%83%BC%E3%83%93%E3%82%B9%E3%81%AF%E3%82%8B%E3%81%AE%E9%A2%A8)の中山5-11-3、共有中心 `38.292133, 140.842529`、D-1の確定順 | `approx`。遊季ガーデンと同一住所で個別ピンを確定できず、共有中心から分離したため | `harunokaze.co.jp` の中山7-15-10が別事業所か確認。加えて、現行`map.png`のラベル順は遊季ガーデン→はるの風に見える一方、D-1ははるの風を上と指定しているため最終確認したい |
| 遊季ガーデン | `38.2921039, 140.8426675`・下 | [nakayaman.com掲載](https://www.nakayaman.com/post/%E9%81%8A%E5%B8%8C%E3%82%AC%E3%83%BC%E3%83%87%E3%83%B3%E6%A0%AA%E5%BC%8F%E4%BC%9A%E7%A4%BE)の中山5-11-3-B（2F）、共有中心 `38.292133, 140.842529`、D-1の確定順 | `approx`。はるの風と同一住所で個別ピンを確定できず、共有中心から分離したため | はるの風との正確な区画位置と上下順 |
| 中杜建設 | `38.2930441, 140.8409565`・上 | [nakayaman.com掲載](https://www.nakayaman.com/post/_%E4%B8%AD%E6%9D%9C%E5%BB%BA%E8%A8%AD)の中山5-19-10と[紙マップ](../map.png)の描画順 | `approx`。同一住所内の個別ピンを確定できず、紙マップ順に共有中心から分離したため | 中杜建設とん daccha とこやの正確な区画位置 |
| ん daccha とこや | `38.2929859, 140.8412335`・下 | [nakayaman.com掲載](https://www.nakayaman.com/post/%E3%82%93-daccha-%E3%81%A8%E3%81%93%E3%82%84)の中山5-19-10と[紙マップ](../map.png)の描画順 | `approx`。同一住所内の個別ピンを確定できず、紙マップ順に共有中心から分離したため | 同上 |
## 再生成後の機械測定

- 共有中心: はるの風／遊季ガーデン = `38.2921330, 140.8425290`、サトー商会／みなとや = `38.2892950, 140.8505400`。各組とも画面座標差は `dx=12.0px`, `dy=22.0px`、上店の `y` が小さく、2店とも `src: approx`。
- B+C位置関係: たけむらや⇔ウエルシア `25.2px`、フラワー中山はたけむらやより `70.0px`上、EndRollはcake NAOより`22.0px`上。`zones=0`、対象4店の`x-tx/y-ty=0.0px`。
- B+C UI保護: `tools/v2-build/preview.template.html` はD着手前後でSHA-256 `8E9250EBFFD3CDE4C59E9EE90900722C29BCE527A419075A14FC95DD1086BFCD`のまま。グラバー`pointerdown`、`setPointerCapture`、`layoutLabels()`を保持し、`innerHTML`一致0件。現在セッションは利用可能ブラウザ0件のため実ブラウザ再試験は未実施。
- 生成: `python tools/v2-build/build_mapdata.py --preview` exit `0`、連続2回SHA-256一致（`preview.html` = `27E511D98867DC2CC328C667F2F11F7053868A1FABCEC87FAF1D5590C9E1D803`）。
- 保護対象: `git diff --stat -- index.html v2.html` exit `0`・出力0行。両ファイルのSHA-256は `16384CD82C346947FB7D59F5F74662657552E0F56EE24BD41A04D103FAEF3D53`。
