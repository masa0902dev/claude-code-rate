# clc - Claude Code レート残量表示 CLI

Zenn記事: https://zenn.dev/masa0902dev/articles/clc-claude-code-rate

`clc rate` を叩くだけで Claude Code のレート残量(5時間枠/週間枠/追加課金枠)を表示する CLI ツールです.
ちなみに`clc`は"Claude Code"の略.

Python3.13にて, 外部パッケージなしで開発しました.

```sh
❯ clc rate
5Hours [██░░░░░░░░░░░]  17.0% used
       resets in 01h59m

Weekly [█░░░░░░░░░░░░]   4.0% used
       resets in 6d,39m

Extra  [███░░░░░░░░░░]  24.6% used
       used $2.46

```
<img src="./img-cmd.png" width="400" alt="私の環境での実際の見た目">


- 使用率に応じてバーが色分けされます.
- 見た目や表示内容のカスタマイズは, `config.json` を編集するだけで可能です.
- `clc xxx` のように他のコマンドを追加することも可能です.
  - 反対に, `clc` だけで`clc rate`を叩くようにすることも容易に可能です. (.zshrcにaliasを追加する等)

## 使い方

Zenn記事をご参照下さい.
該当部分のリンクです: https://zenn.dev/masa0902dev/articles/clc-claude-code-rate#%E4%BD%BF%E3%81%84%E6%96%B9

## 仕組み

`https://api.anthropic.com/api/oauth/usage` に OAuth トークン(`anthropic-beta: oauth-2025-04-20` ヘッダ付き)で GET し, `five_hour` / `seven_day` 各ウィンドウの `utilization`(使用率%)と `resets_at`(リセット時刻)を整形して表示します.

### extra_usage について

自分の場合, 月に10\$迄に追加クレジット利用を制限しています(monthly_limitの値).
なので例えば, 24.6% used なら今月はあと7.54$使えるということです.

```json
"extra_usage": {
    "is_enabled": true,
    "monthly_limit": 1000,
    "used_credits": 246.0,
    "utilization": 24.6,
    "currency": "USD",
    "decimal_places": 2,
    "disabled_reason": null,
    "daily": null,
    "weekly": null
  },
```


## 参考
https://qiita.com/tatsuya582/items/5ca0c12a8495530f7d09

