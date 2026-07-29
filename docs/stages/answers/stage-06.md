# Stage 6 演習課題 解答

[stage-06-security.md](../stage-06-security.md) の演習課題3問への解答です。
先に自分で予想してから読んでください。

## 問1: `run:` への直接埋め込みと `env:` 経由で、インジェクションを試みた PR タイトルを与えるとどうなるか

**予想**: `run:` の中の `${{ }}` はシェルが起動する前に文字列として展開されるため、
直接埋め込んだ側は PR タイトルの中身がシェルの構文として解釈され、`"; echo INJECTED; #`
の `;` がコマンドの区切りとして働き、`echo INJECTED` が別コマンドとして実行されて
しまうはずです。`env:` 経由の側は、タイトルが環境変数の**値**として渡るだけなので、
`;` や `#` はただの文字として扱われ、実行されないはずです。

**実際に確かめる**: `stage/06-security` ブランチ上で、`ci.yml` に直接埋め込みの例と
`env:` 経由の例を両方持つ一時的なジョブ（`injection_experiment`）を追加しました
（commit `d56bb6a`）。続けて PR #21 のタイトルを

```
Stage 6: セキュリティ基礎"; echo INJECTED; #
```

に変更してから push し、実行 ID `30409290745` をトリガーしました
（タイトル変更は `gh api repos/.../issues/21/events` の `renamed` イベントとして
2026-07-28T23:50:52Z に記録されています）。

直接埋め込みのステップで実際に生成・実行されたスクリプトと、その出力は次のとおりです。

```
Run echo "PR Title (direct): Stage 6: セキュリティ基礎"; echo INJECTED; #"

PR Title (direct): Stage 6: セキュリティ基礎
INJECTED
```

`;` で区切られた2つのコマンドとして実行され、`INJECTED` という、`run:` に書いた覚えの
ない文字列がログに出力されました。一方、`env:` 経由のステップは次のとおりです。

```
Run echo "PR Title (env): ${PR_TITLE}"
env:
  PR_TITLE: Stage 6: セキュリティ基礎"; echo INJECTED; #

PR Title (env): Stage 6: セキュリティ基礎"; echo INJECTED; #
```

`PR_TITLE` という環境変数の値としてタイトル文字列がまるごと渡り、出力は1行のまま、
`;` や `#` はただの文字として印字されただけでした。

**予想どおりの結果でしたが、CI 全体が落ちた理由は予想と少し違いました。**
`injection_experiment` ジョブ自体は3秒で成功しましたが、`Checks / Static Checks` の
「ワークフローを actionlint で検査する」ステップが次のメッセージで失敗し、それに伴って
`Lint & Test` も失敗しました。

```
.github/workflows/ci.yml:110:43: "github.event.pull_request.title" is potentially
untrusted. avoid using it directly in inline scripts. instead, pass it through an
environment variable. see https://docs.github.com/en/actions/reference/security/secure-use#good-practices-for-mitigating-script-injection-attacks
for more details [expression]
```

つまり、**実行時にインジェクションが成立したことに加えて、`actionlint` 自身が
静的にこの危険なパターンを検出し、CI を落としていました。** `actionlint` は
Stage 5 から `static` ジョブに組み込まれているため、`env:` を使わずに
`github.event.pull_request.title` のような外部由来の値を `run:` に直接埋め込むと、
実行前の段階で食い止められることが実測で確認できました。

**解答**: `run:` 内の `${{ }}` はシェル起動前の文字列展開であり、外部から来る値を
直接埋め込むと任意のシェル構文として解釈され得ます（今回のように `;` や `#` を
含む値であれば、追加のコマンド実行やコメントアウトが成立します）。`env:` に
一度置いてから `${ENV_VAR}` としてシェル側で参照すれば、値は環境変数の中身として
渡るだけで、シェルの構文としては解釈されません。加えて `actionlint` の
`expression` ルールが、既知の「信頼できないコンテキスト」（PR タイトルや本文など）を
`run:` に直接埋め込むパターン自体を静的に検出するため、二重の防御になっています。

確認後、実験ジョブは `git revert --no-edit HEAD` で完全に取り除き（commit `cf0c7e1`）、
PR タイトルも `renamed` イベントのとおり元の `Stage 6: セキュリティ基礎` に戻しました。
実行 ID `30409444697` で全チェックが green に戻ったことを確認しています。

## 問2: `zizmor` の指摘を1つ意図的に再導入する

**予想**: SHA でピン留めした `uses:` を1つタグ参照に戻せば、`zizmor` の
`unpinned-uses`（Task 3 で解消済みのはずの指摘）が再び報告され、`Static Checks`
ジョブが失敗するはずです。

**実際に確かめる**: `.github/actions/setup-python-env/action.yml` の

```
uses: astral-sh/setup-uv@37802adc94f370d6bfd71619e3f0bf239e1f3b78  # v7.6.0
```

を

```
uses: astral-sh/setup-uv@v7
```

に戻して push しました（commit `576e66b`、実行 ID `30410516553`）。
`Checks / Static Checks` の「ワークフローをセキュリティ観点で検査する」ステップが
次の内容で失敗しました。

```
error[unpinned-uses]: unpinned action reference
   --> .github/actions/setup-python-env/action.yml:20:13
    |
 20 |       uses: astral-sh/setup-uv@v7
    |             ^^^^^^^^^^^^^^^^^^^^^ action is not pinned to a hash (required by blanket policy)
    |
    = note: audit confidence → High
    = help: audit documentation → https://docs.zizmor.sh/audits/#unpinned-uses

2 findings (1 suppressed): 0 informational, 0 low, 0 medium, 1 high
```

終了コードは `14`（`zizmor` は少なくとも1件の error 相当の指摘があると `14`
で終了する。問3で確認した warning のみのケースは `13` で終了しており、この違いも
実測できました）。`Lint & Test` も、依存ジョブの結果判定ステップにより失敗しました。

**予想どおりの結果です。** SHA ピン留めをタグ参照に戻すと、`unpinned-uses`
（`audit confidence → High`）が即座に再現し、CI が赤くなりました。

確認後、`git revert --no-edit HEAD`（commit `10ad4df`）で `action.yml` を SHA 参照に
戻し、`git diff` で revert 前のコミットと差分が無いことを確認しました。実行 ID
`30423260212` で全チェック（`Metadata` / `Checks / Static Checks` / `Checks / Test`
×3 / `Lint & Test` の6件）が green に戻ったことを確認しています。

## 問3: `permissions` をトップレベルから削除すると何が起きるか予想し、確かめる

**予想**: `permissions:` を削除すると、`GITHUB_TOKEN` の権限はこのリポジトリの
既定設定に委ねられます。既定がこのリポジトリで何になっているかは、書いてみるまで
（あるいは `gh api` で確認するまで）分かりません。もし既定が `read` であれば
CI は見た目上壊れないはずですが、「ワークフローを読むだけでは権限が分からない」
という状態そのものが問題になるはずです。

まず `gh api repos/jane1210jane/githubactions-sample1/actions/permissions/workflow`
を実行し、次の結果を得ました。

```
{"default_workflow_permissions":"read","can_approve_pull_request_reviews":false}
```

このリポジトリの既定は `read` でした。

**実際に確かめる**: `ci.yml` の `permissions:` ブロック（`contents: read` と、その
上の説明コメント、計9行）をまるごと削除して push しました（commit `96bf452`、
実行 ID `30459601411`）。

CI は失敗しました。原因は `Checks / Static Checks` の「ワークフローをセキュリティ
観点で検査する」ステップで、`zizmor` が次の4件（`ci.yml` 全体1件と、`meta`・
`checks`・`gate` の3ジョブそれぞれに1件ずつ）を報告したことです。

```
warning[excessive-permissions]: overly broad permissions
 --> .github/workflows/ci.yml:4:1
    default permissions used due to no permissions: block
    (note: audit confidence → Medium)

warning[excessive-permissions]: overly broad permissions
 --> .github/workflows/ci.yml:20:3
    default permissions used due to no permissions: block

warning[excessive-permissions]: overly broad permissions
 --> .github/workflows/ci.yml:43:3
    default permissions used due to no permissions: block

warning[excessive-permissions]: overly broad permissions
 --> .github/workflows/ci.yml:50:3
    default permissions used due to no permissions: block

5 findings (1 suppressed): 0 informational, 0 low, 4 medium, 0 high
```

（`ci.yml:4:1` はワークフロー全体、`ci.yml:20:3` は `meta` ジョブ、`ci.yml:43:3` は
`checks` ジョブ、`ci.yml:50:3` は `gate` ジョブへの指摘です。）

終了コードは `13`（warning のみで error が無いケース。問2の `unpinned-uses`
は `high` の error 相当で終了コード `14` でした）。`Lint & Test` も依存ジョブの
判定により失敗しました。

さらに、`Metadata` ジョブのログの `GITHUB_TOKEN Permissions` セクションを確認すると、

```
Contents: read
Metadata: read
Packages: read
```

`permissions:` を明示していたときには無かった **`Packages: read`** が新たに
付与されていることが分かりました（明示していた状態のログでは `Contents: read`
と `Metadata: read` の2つだけでした）。

**予想は半分当たり、半分は予想以上でした。** CI が見た目上「壊れる」かどうかは
このリポジトリの既定設定（`read`）次第で、実際、テストやフォーマットの検査自体は
すべて通っていました。しかし `zizmor` が `excessive-permissions` を4件報告して
`Static Checks` を落としたため、**結果として CI は失敗しました。** さらに、
`Packages: read` が黙って追加されていたという事実は、「既定に頼ると、実際に
どの権限が渡っているかはワークフローファイルを読むだけでは分からない」ことを
直接示しています。`zizmor` はこのリポジトリの既定が何かを知らない（オフラインで
ワークフローファイルだけを静的に見ている）ため、`permissions:` が無いこと自体を
「このワークフローがどこか別のリポジトリにコピーされたり、リポジトリの既定設定が
変わったりした場合に、意図せず広い権限を持ちかねない」リスクとして扱っています。

確認後、`git revert --no-edit HEAD`（commit `a426b85`）で `permissions:` ブロックを
復元し、`git diff` で revert 前のコミットと差分が無いことを確認しました。実行 ID
`30459768352` で全チェックが green に戻ったことを確認しています。
