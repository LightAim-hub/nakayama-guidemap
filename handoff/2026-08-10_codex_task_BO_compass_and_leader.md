# BO: 方位記号の向きを直す ＋ 二列の引き出し点線を消す

商店街の担当者（あみさん）から2件。どちらも入口・地図の見た目。
`gate.py` に **N61「方位記号の針が北を向いている」**を足したので、いまは **FAIL 1件**。

## 触ってよい / いけない

- 触る: `tools/v2-build/template.html`
- **触らない: `tools/v2-build/gate.py` / `index.html` / `v2.html` / `mapdata.json` / `official_details.json`**

## 1. 方位記号の針が 92.8度 ずれている

```js
// 方位記号の針を北へ向ける。投影は rot_deg だけ回してあるので、その分だけ戻す。
(function orientCompass(){
  const needle = document.getElementById('compassNeedle');
  const rot = GEO.meta && GEO.meta.proj ? GEO.meta.proj.rot_deg : 0;
  if (needle && rot) needle.setAttribute('transform', 'rotate(' + (-rot) + ' 22 22)');
})();
```

**考え方が逆になっている。** 針が指すべきなのは「地図の回転を戻した向き」ではなく
**「北へ1m進んだとき、画面がどっちへ動くか」**。

投影は `x = mx*cos(R) + my*sin(R)` / `y = mx*sin(R) - my*cos(R)`（`R = rot_deg = 46.4°`、
`mx`=東へのm、`my`=北へのm）。北 `(mx,my)=(0,1)` を入れると
画面ベクトルは `(sin R, -cos R)` = 真上から**時計回りに 46.4度**。

実測（`gate.py` の N61 と、`trace_overlay.py` の逆投影の両方で確認済）:

| | 値 |
|---|---|
| いまの針 | 真上から時計回り 313.6度（＝ `rotate(-46.4)`） |
| 北の向き | 真上から時計回り **46.4度** |
| ずれ | **92.8度** |

`rotate()` の符号を直すこと。**コメントも直す**こと（いまのコメントが間違いの原因なので、
そのまま残すと次の人がまた同じ向きに戻す）。

## 2. 二列カードの引き出し点線を消す

入口（通り沿いの二列）で、カードを本来の位置からずらした時に出る短い破線:

```css
#strip .strip-row.displaced::after{ content:""; position:absolute; top:calc(50% + var(--leader-offset,0px));
  width:22px; border-top:2px dashed rgba(122,92,59,.62); pointer-events:none; }
#strip .strip-row.displaced[data-side="west"]::after{ left:100%; }
#strip .strip-row.displaced[data-side="east"]::after{ right:100%; }
```

**この破線を出さないようにする。** ボスの指示（実機写真で3箇所に丸印）。

- `.displaced` クラス自体と `--leader-offset` の計算は**残す**こと。位置ずれの量は
  レイアウト側（`layoutStripRows`）が使っている値で、消すと配置が変わる。
  **消すのは見た目の破線だけ。**
- 通り沿いの道路の破線・`.strip-road-label` は別物なので**触らない**（写真の赤丸は
  カードの横に出ている短い横線のみ）。

## 合格条件

1. `python tools/v2-build/build_mapdata.py` が通る
2. `python tools/v2-build/gate.py --target index.html` が **PASS（違反0件・N1〜N61）**
3. 二列の画面で `.strip-row.displaced::after` が描かれていないこと
   （`getComputedStyle(el,'::after').content` が `none` 等）。実測値を result.txt に書く
4. 歩ける店 60/60 / JSエラー 0
