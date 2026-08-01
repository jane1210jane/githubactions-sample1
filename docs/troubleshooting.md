# トラブルシューティング索引

GitHub Actions の失敗は、ローカルと違って手元で再現しづらいのが最大のつまずき要因です。
**Actions のログに出た文字列**から引けるように並べています。

## 引き方

1. Actions タブ → 失敗したワークフロー実行 → 赤い ✗ のジョブをクリック
2. 赤くなっているステップを展開する
3. そこに出ている文字列を、このページ内で検索する

## 症状から引く

### `ModuleNotFoundError: No module named 'sales_report'`

**原因**: `actions/checkout` を書き忘れているか、依存のインストール前にテストを実行している。
**対処**: `uses: actions/checkout@v7` が最初のステップにあるか、`uv sync --locked` の後に
`uv run pytest` が来ているかを確認する。

### `The lockfile at 'uv.lock' needs to be updated`

**原因**: `pyproject.toml` を変更したのに `uv.lock` を更新していない。`--locked` はこのズレを検出する。
**対処**: ローカルで `uv lock` を実行し、`uv.lock` をコミットして push する。

### `Error: Process completed with exit code 1`

**原因**: ステップのコマンドが 0 以外で終了した。これは結果であって原因ではない。
**対処**: このメッセージの**すぐ上**の行を読む。テストの失敗内容や lint の指摘がそこに出ている。

### `Changes must be made through a pull request`

**原因**: ruleset により、デフォルトブランチへの直接 push が禁止されている。
**対処**: 意図した動作。ブランチを切って PR を出す。
`git switch -c fix/xxx && git push -u origin fix/xxx && gh pr create`

### 日本語が文字化けする

**原因**: Windows のコマンドプロンプトや PowerShell の既定のコンソールコードページが
UTF-8 になっていない（多くの場合 CP932）。`sales-report` や pytest の出力に含まれる
日本語がそのコードページで正しく表示できず、記号の羅列のように化ける。
**対処**: 実行前にコンソールを UTF-8 に切り替える。

```powershell
chcp 65001
```

または、そのプロセスだけ `PYTHONIOENCODING` で明示的に UTF-8 を指定する。

```powershell
$env:PYTHONIOENCODING = "utf-8"
```

詳しくは README の「Windows で進める場合」を参照。

### PR が「Expected — Waiting for status to be reported」から進まない

**原因**: 必須チェックに指定した名前のジョブが、その PR では起動していない。
`paths` / `paths-ignore` フィルタでワークフロー自体がスキップされると、
チェックは「未報告」のまま永久に待ち続ける。
**対処**: `pull_request` トリガーには `paths` フィルタを付けない。
どうしても付けたい場合は、常に成功する集約ジョブを 1 つ用意し、そちらを必須チェックにする
（この設計はモノレポ化する Stage 9 で扱う）。

### 必須チェックが「Expected — Waiting for status to be reported」のまま進まない（ジョブを分割した後）

**原因**: ジョブ構成を変えた結果、ruleset が要求している名前のジョブが存在しなくなった。
必須チェックはジョブの `name:` に紐づく。
**対処**: 必須チェックと同じ名前を持つジョブが1つ存在するか確認する。
本教材では集約ジョブ `gate` が `name: Lint & Test` を引き継いでいる。

### 集約ジョブが skipped になり、必須チェックが報告されない

**原因**: `needs:` の依存ジョブが失敗すると、既定では後続ジョブは実行されず `skipped` になる。
skipped は success でも failure でもないため、必須チェックは「未報告」のままになる。
**対処**: 集約ジョブに `if: always()` を書き、依存の結果を自分で判定して明示的に失敗させる。

### Python バージョンが `requires-python` と食い違う（ログに `which is incompatible with the project's Python requirement` と出る）

**原因**: matrix に指定した Python バージョンが `pyproject.toml` の `requires-python` を満たしていない。
本教材には `.python-version` ファイルは無く、`astral-sh/setup-uv` の `with.python-version`
（`ci.yml` の `matrix.python-version`）が要求元になっているため、エラー文の主語は
`.python-version` ではなく「requested interpreter（要求したインタプリタ）」になる。
末尾のパッチバージョン（例のメッセージでは `3.11.15`）は、その時点で `uv` が解決した
実際のパッチリリースにより変わる。
**対処**: matrix の値か `requires-python` のどちらかを直す。
matrix は「対応を宣言した範囲」と一致させる。

### `FAIL Required test coverage of 80% not reached`

**原因**: カバレッジが `--cov-fail-under` で指定した閾値を下回った。
**対処**: テストを足すか、閾値の妥当性を見直す。
「とりあえず閾値を下げる」を繰り返すとゲートの意味が失われるので、下げるときは理由を残す。

### `Required property is missing: shell`

**原因**: composite action の `run:` ステップに `shell:` を書いていない。
ワークフローの `run:` と違い、composite action では既定値が無い。
**対処**: `shell: bash` を付ける。Windows ランナーでは Git for Windows 同梱の bash が
使われるため、bash のままでも動く（詳しくは Stage 5 の「つまずきポイント」）。
PowerShell 前提のコマンドを書きたいときだけ `shell: pwsh` にする。

### reusable workflow を導入したら必須チェックが報告されなくなった

**原因**: reusable workflow を呼ぶと、呼び出し先のジョブ名は
`<呼び出し側ジョブ名> / <呼び出し先ジョブ名>` に変わる。
必須チェックに指定していた名前が呼び出し先にあると、その名前は現れなくなる。
**対処**: 必須チェックにするジョブは呼び出し側に残す。
本教材では集約ジョブ `gate`（`name: Lint & Test`）を `ci.yml` 側に置いている。

### ステップサマリや式の値が空欄になる

**原因**: `${{ needs.foo.outputs.bar }}` のような参照は、対象が存在しなくてもエラーにならず
空文字列に評価される。綴り間違いや消し忘れが無言で通る。
**対処**: `actionlint` が存在しないコンテキスト参照を指摘する。`Static Checks` のログを確認する。

### `GraphQL: Resource not accessible by integration (addComment)`

**原因**: `permissions: contents: read` のとき、`GITHUB_TOKEN` で PR にコメントを
書こうとするなど、書き込みを伴う API 呼び出しを行った。GraphQL の `addComment`
に限らず、権限が足りない操作全般で同じ形式のメッセージが出る。
**対処**: 必要な権限（この例では `pull-requests: write`）を、ワークフロー全体では
なく、その操作を行う**ジョブだけ**に足す。トップレベルに足すと `zizmor` の
`excessive-permissions` に拒否されることがある（次項参照）。詳しくは
[Stage 6 の解説](stages/stage-06-security.md) を参照。

### `Static Checks` が `zizmor` のステップで落ちる（`error[...]` / `warning[...]` が出る）

**原因**: `zizmor` がワークフローの危険な書き方を検出した。代表的なものに
`unpinned-uses`（`uses:` がタグ参照のままで SHA にピン留めされていない）、
`excessive-permissions`（`permissions:` が広すぎる、あるいは書かれておらず既定に
頼っている）、`artipacked`（`actions/checkout` が認証情報をワークスペースに
残したままになっている）がある。`error`/`warning` の表示と終了コードは
**`severity`**（`informational` / `low` / `medium` / `high`）で決まり、`high` は
`error`・終了コード `14`、`medium` は `warning`・終了コード `13`（`low` は `12`、
`informational` は `11`、指摘が無ければ `0`）になる。`audit confidence`
（`low` / `medium` / `high`、「どれだけ確からしいか」）は severity とは独立した
別の軸で、`error`/`warning` の判定には関係しない。実際に `pull_request_target`
トリガーを検出する `dangerous-triggers` は `audit confidence → Medium` でも
severity は `high`（`error`、終了コード `14`）になる。`--min-severity` /
`--min-confidence` でそれぞれ独立に絞り込める。
**対処**: 抑制コメント（`# zizmor: ignore`）は使わず、コード側を直す。`uses:` は
SHA + バージョンコメントに、`permissions:` は必要な範囲だけをジョブ単位で明示する、
`actions/checkout` には `persist-credentials: false` を足す、など指摘の種類に応じて
対応する。詳しくは [Stage 6 の解説](stages/stage-06-security.md) を参照。

### `Failed to save: Unable to reserve cache with key ..., another job may be creating this cache.`

**原因**: `actions/cache`（または `actions/cache/save`）の `key:` に、内容ハッシュ
（`hashFiles(...)`）のように**内容が変わらない限り毎回同じ値になる鍵**を使っている。
`restore` がその鍵に完全一致して復元した直後、同じ鍵で `save` しようとするが、
`actions/cache` の鍵は一度書き込むと不変で上書きできないため、必ず失敗する。
これは一時的な不具合ではなく、対象ファイルの内容が変わらない限り毎回起こる。
**対処**: 鍵にコミットごとに変わる値（`github.sha` など）を使う。ただし同一コミットに
対する2回目の実行や re-run では、それでも鍵が一致し同じ理由で失敗しうる。
詳しくは [Stage 7 の解説](stages/stage-07-container.md) と
[演習2の解答](stages/answers/stage-07.md) を参照。

### `error[cache-poisoning]: runtime artifacts potentially vulnerable to a cache poisoning attack`

**原因**: `zizmor` が、同一ジョブ内に「キャッシュを書き込むアクション」
（`actions/cache` など）と「ビルド成果物を外部へ送り出す（publish する）アクション」
（`docker/build-push-action` など）が同居していることを検出した。`push:` を
条件式でガードしていても、`zizmor` はステップの `if:` 条件を評価しないため、
ガードの有無に関わらず対象アクションの組み合わせだけで検出する。
**対処**: `actions/cache` を `actions/cache/restore`（読み取り、常時実行）と
`actions/cache/save`（書き込み、信頼できるコンテキストに限定）に分割する。
`zizmor` がキャッシュ対応アクションとして認識する一覧はサブパス無しの完全一致
（`actions/cache`）だけを含むため、サブパス付きの参照（`actions/cache/restore` /
`actions/cache/save`）はこのパターンに当てはまらなくなり、finding が消える。
**ただしこれはリスククラスそのものの解消ではなく、静的解析のパターンマッチが
対象から外れただけである点に注意する。** 詳しくは
[Stage 7 の解説](stages/stage-07-container.md) を参照。

### `Could not assume role with OIDC: Not authorized to perform sts:AssumeRoleWithWebIdentity`

**原因**: GitHub からトークンは届いているが、AWS 側の信頼ポリシーがそのトークンの
`sub` クレームを許可していない。**「AWS まで到達したが断られた」状態**であり、
GitHub 側の `permissions` は正しい。よくあるのは次の3つ。

1. **ジョブに `environment:` を付けた。** environment を指定したジョブの `sub` は、
   トリガーが何であれ `<prefix>:environment:<環境名>` になり、ref の形は現れない。
   信頼ポリシーが `ref:refs/heads/main` しか許可していないと、environment を持たない
   ジョブだけが成功し、デプロイのジョブだけが落ちる、という非対称な失敗になる。
2. **`main` 以外のブランチから実行した。** `sub` の ref 部分が一致しない。
3. **信頼ポリシーの `sub` が旧形式（数値 ID 無し）で書かれている。**

**対処**: [docs/aws-bootstrap.md](aws-bootstrap.md) 3.2 節の手順で、実際に発行される
`sub` を `gh api repos/<OWNER>/<REPO>/actions/oidc/customization/sub` で確認し、必要な
`sub` をすべて信頼ポリシーに列挙する（`StringEquals` の値は配列にできる）。
**`sub` を `*` で緩めて回避しないこと。** ロールを作り直す必要はなく、
`aws iam update-assume-role-policy` で信頼ポリシーだけを差し替えられる。

### `Credentials could not be loaded, please check your action inputs: Could not load credentials from any providers`

**原因**: `aws-actions/configure-aws-credentials` が OIDC トークンを取得できていない。
**AWS へリクエストが飛ぶ前の失敗**で、ほぼ確実にジョブへの `id-token: write` の
付け忘れである。同じログの少し上に、action 自身が出す次のヒントが（`##[error]` ではなく
通常のログ行として）出ている。

```
It looks like you might be trying to authenticate with OIDC.
Did you mean to set the `id-token` permission?
```

**対処**: そのジョブの `permissions:` に `id-token: write` を足す。トップレベルに
書いてもよいが、必要なジョブにだけ足すほうが Stage 6 の原則に沿う。なお、この失敗は
12回リトライして約80秒かけてから確定するので、一時的なネットワーク障害と誤解しない
こと。詳しくは [Stage 8 の解説](stages/stage-08-aws-deploy.md) と
[演習1の解答](stages/answers/stage-08.md) を参照。

### `Could not assume role with OIDC: connect ETIMEDOUT <IP>:443`

**原因**: STS のエンドポイントへの TCP 接続が成立していない。**AWS に届いていない**ので、
設定（`permissions` も信頼ポリシーも）は何も間違っていない。ランナーと AWS の間の
一時的なネットワーク障害である。

**対処**: 何も直さず再実行する。実測では、1回の試行が約6分半ハングし、2回リトライした
ところでジョブの `timeout-minutes: 20` に達して打ち切られ、同じ手順の再実行では成功した。
**このエラーを設定ミスと誤認して信頼ポリシーを編集すると、正しい設定を壊す。** 同じ
「認証できない」でも、`Not authorized to perform sts:AssumeRoleWithWebIdentity`（届いたが
拒否）や `Could not load credentials from any providers`（トークンを要求できていない）とは
対処が異なる。切り分け表は [演習2の解答](stages/answers/stage-08.md) を参照。

### `Deploy` の実行が `waiting` のまま進まない / production が始まらない

**原因**: 失敗ではない。`production` environment に承認者（`required_reviewers`）が
設定してあるため、人が承認するまでジョブが開始されない。`gh run view <id> --json jobs`
では `Deploy to production=waiting/-` と表示される。

**対処**: Actions 画面の該当実行にある **Review deployments** から承認する。
`gh api repos/<OWNER>/<REPO>/actions/runs/<id>/pending_deployments` で承認待ちの環境と
自分が承認できるかを確認できる。**放置すると期限切れになる**ので、承認待ちであることに
気づけるようにしておくこと。
