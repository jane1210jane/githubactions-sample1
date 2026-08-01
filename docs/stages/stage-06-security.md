# Stage 6: セキュリティ基礎

## 1. このステージのゴール

Stage 1 から書き続けてきた `permissions:` と、Stage 0 から `hello.yml` に置いていた
`env:` 経由の一手間には、どちらも「なぜ必要か」を明言しないコメントを残してきました。
このステージでは、その2つの理由を実測とともに理解し、加えて「依存する他人のコードを
固定する」（SHA ピン留めと Dependabot）「ワークフロー自体をセキュリティ観点で検査する」
（`zizmor`）という2つの仕組みを追加します。到達点は、CI が持つ書き込み権限つきの
トークンと、毎回ダウンロードして実行する他人のコードの両方に対して、具体的な脅威像を
持てるようになることです。

## 2. 前提

- `stage-05` が完了していること。`meta` / `checks`（`static` + `test` を呼ぶ）/ `gate`
  の3ジョブ構成で CI が動き、composite action と reusable workflow への切り出しが
  済んでいる状態です。

## 3. なぜ必要か

`stage-00` から `stage-05` まで、CI が「壊れていないか」だけを見てきました。フォーマット、
lint、型、テスト、カバレッジ——すべて「動くか」の検査です。しかし CI はそれ以上のものを
握っています。各ジョブは `GITHUB_TOKEN` という、リポジトリに対してある範囲の操作を行える
トークンを自動発行されて実行されますし、PR の内容（タイトルや本文）のような外部から来る
値をワークフローの中で扱いますし、`actions/checkout` や `astral-sh/setup-uv` のような
他人が書いたコードを毎回ダウンロードして実行します。これらは「壊れていない」CI でも
起こり得る危険です。**構文的に正しく、テストも通っているワークフローが、同時に危険な
構成であることは十分あり得ます。** このステージは、その2つの軸（トークンの権限、他人の
コード）を最小化・固定・検査する方法を扱います。

## 4. 手順

以下は実際に行った手順です（このドキュメントでは内部の管理番号ではなく実施内容で示します）。

### 手順A: サードパーティ action の SHA ピン留めと Dependabot

`actions/checkout@v7`・`actions/upload-artifact@v7`・`astral-sh/setup-uv@v7` の3つの
タグ参照について、`gh api repos/<repo>/commits/<tag> --jq .sha` で対応する SHA を解決し、
`gh api repos/<repo>/tags --jq '.[] | select(.commit.sha=="<sha>") | .name'` で
その SHA が実際にどのバージョンタグに対応するかを確認しました。`astral-sh/setup-uv` は
`releases/latest` が `v9.0.0` を返しましたが、これは今回解決した SHA（`@v7` が指す
時点のもの）とは一致しないため採用せず、tags API で実際にその SHA を指しているタグ名
（`v7.6.0`）をバージョンコメントに採用しました。**`releases/latest` を鵜呑みにしない**
というのがここでの実務上の教訓です。4ファイルの `uses:` を SHA + バージョンコメントの
形式に置き換え（`hello.yml` には `uses:` が1つも無いため変更なし）、`.github/dependabot.yml`
を新規作成しました（commit `e475b09`）。push 後、PR のチェック一覧に
`.github/dependabot.yml`（Dependabot config file validation）という検証チェックが
新規に1件追加され、`conclusion: success` だったことを `gh api repos/.../commits/<sha>/check-runs`
で確認し、`package-ecosystem: uv` が実際に受理される設定であることの直接証拠としました。

### 手順B: `zizmor` の導入と検査ステップの追加

`pyproject.toml` の `dev` 依存に `zizmor>=1.0` を追加し、`uv sync` で
`zizmor==1.28.0` を解決しました。`uv run zizmor .github/workflows/ .github/actions/`
をローカルで実行したところ、`actions/checkout` を使う3箇所すべてで `artipacked`
（`persist-credentials` が既定で有効なままになっている）を指摘されたため、抑制コメントは
一切使わず、各 `actions/checkout` に `persist-credentials: false` を追加して直しました。
その後、`static` ジョブの「ワークフローを actionlint で検査する」ステップの直後に、
`zizmor` を実行するステップを追加しました（commit `0755bb2`）。

### 手順C: `permissions` の効果を実測する

`gate` ジョブに、PR へコメントを書こうとするだけの一時的なステップを追加し、push しては
結果を記録し、確認後に revert する、という手順を複数回踏みました。最初の試行
（`contents: read` のまま、`GH_REPO` を渡さない状態）は失敗しましたが、実際のエラーは
`fatal: not a git repository (or any of the parent directories): .git` で、`permissions`
とは無関係でした。原因は `gate` ジョブが一度も `actions/checkout` を実行していないため、
`gh` CLI がリポジトリを特定する手段（`--repo` フラグ・`GH_REPO` 環境変数・`git remote`
のいずれか）を持たなかったことです。実験ステップの `env:` に
`GH_REPO: ${{ github.repository }}` を足してこの交絡要因を切り離した上でやり直したところ
（run `30408370634`）、次のエラーで失敗しました。

```
GraphQL: Resource not accessible by integration (addComment)
```

続けて、トップレベルの `permissions` に `pull-requests: write` を足すことも試しましたが、
この変更は `zizmor` の `excessive-permissions`（後述）が `high` の severity（`error`、
終了コード `14`）として報告し拒否したため、代わりに
`gate` ジョブだけに job-scoped の `permissions: { contents: read, pull-requests: write }`
を足したところ成功し、実際に PR #21 へ `github-actions` bot 名義のコメントが投稿された
ことを確認しました（確認後は削除済み）。最終的に、実験ステップと job-scoped
`permissions` の両方を完全に revert しています（`git diff` で差分ゼロを確認）。

## 5. 何が変わったか

このステージ完了時点（タグ `stage-06`）の `ci.yml` と `reusable-python-ci.yml` を
以下に転記します。行番号引用はすべてこのブロックの行を指します。

`ci.yml`（`.github/workflows/ci.yml`）:

<!-- transcript: .github/workflows/ci.yml @ stage-06 -->
```
1| # Stage 1 で CI を追加し、Stage 2 でトリガーを設計し、Stage 3 でジョブを3層に分け、
2| # Stage 4 で品質ゲートを入れ、Stage 5 で検査とテストを再利用可能ワークフローへ切り出した。
3| # このファイルに残っているのは「いつ動かすか」と「何を必須とするか」だけ。
4| name: CI
5| 
6| on:
7|   pull_request:
8|     branches: [main]
9|   push:
10|     branches: [main]
11|     paths-ignore:
12|       - "docs/**"
13|       - "**/*.md"
14| 
15| concurrency:
16|   group: ${{ github.workflow }}-${{ github.ref }}
17|   cancel-in-progress: ${{ github.event_name == 'pull_request' }}
18| 
19| # permissions: このワークフローが GITHUB_TOKEN に許す操作。
20| # GITHUB_TOKEN はジョブごとに自動発行され、既定の権限はリポジトリ設定に依存する。
21| # ここで contents: read を明示することで、設定に関係なく「読むことしかできない
22| # トークン」に固定している。書き込みが必要なジョブが出てきたら、ワークフロー
23| # 全体ではなくそのジョブだけに permissions を足す（理由と実測は
24| # docs/stages/stage-06-security.md を参照）。
25| permissions:
26|   contents: read
27| 
28| jobs:
29|   meta:
30|     name: Metadata
31|     runs-on: ubuntu-latest
32|     timeout-minutes: 5
33|     outputs:
34|       version: ${{ steps.read.outputs.version }}
35|     steps:
36|       - name: リポジトリを取得する
37|         uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
38|         with:
39|           # このワークフローは checkout 後に git push をしないので、
40|           # 認証情報をワークスペースに残す必要が無い（zizmor: artipacked）。
41|           persist-credentials: false
42| 
43|       - name: pyproject.toml からバージョンを読む
44|         id: read
45|         run: |
46|           version=$(grep -m1 '^version = ' pyproject.toml | cut -d '"' -f 2)
47|           echo "読み取ったバージョン: ${version}"
48|           echo "version=${version}" >> "${GITHUB_OUTPUT}"
49| 
50|   # 再利用可能ワークフローの呼び出し。同じリポジトリ内なので ./ で参照できる。
51|   # jobs.<id>.uses を使うジョブには steps を書けない。呼び出しそのものがジョブになる。
52|   checks:
53|     name: Checks
54|     uses: ./.github/workflows/reusable-python-ci.yml
55| 
56|   # 集約ゲート。ruleset が必須チェックとして見ているのはこのジョブの name。
57|   # 呼び出し先のジョブ名は `Checks / Static Checks` のように変わるが、
58|   # この名前さえ保てば ruleset を触らずに済む。
59|   gate:
60|     name: Lint & Test
61|     runs-on: ubuntu-latest
62|     needs: [meta, checks]
63|     if: always()
64|     timeout-minutes: 5
65|     steps:
66|       - name: 結果をステップサマリに書く
67|         env:
68|           APP_VERSION: ${{ needs.meta.outputs.version }}
69|           CHECKS_RESULT: ${{ needs.checks.result }}
70|         run: |
71|           {
72|             echo "## CI 結果"
73|             echo ""
74|             echo "| 項目 | 値 |"
75|             echo "| --- | --- |"
76|             echo "| バージョン | ${APP_VERSION} |"
77|             echo "| 検査とテスト | ${CHECKS_RESULT} |"
78|           } >> "${GITHUB_STEP_SUMMARY}"
79| 
80|       - name: PR 向けの案内を出す
81|         if: github.event_name == 'pull_request'
82|         run: |
83|           {
84|             echo ""
85|             echo "カバレッジの詳細は Artifacts の \`coverage-html-*\` を開いてください。"
86|           } >> "${GITHUB_STEP_SUMMARY}"
87| 
88|       - name: 依存ジョブの結果を判定する
89|         env:
90|           DEPENDENCY_RESULTS: ${{ join(needs.*.result, ' ') }}
91|         run: |
92|           echo "依存ジョブの結果: ${DEPENDENCY_RESULTS}"
93|           read -ra results <<< "${DEPENDENCY_RESULTS}"
94|           for result in "${results[@]}"; do
95|             if [ "${result}" != "success" ]; then
96|               echo "success ではない依存ジョブがあります"
97|               exit 1
98|             fi
99|           done
100|           echo "すべての依存ジョブが success です"
```

`reusable-python-ci.yml`（`.github/workflows/reusable-python-ci.yml`）:

<!-- transcript: .github/workflows/reusable-python-ci.yml @ stage-06 -->
```
1| # 再利用可能ワークフロー。
2| # workflow_call で呼ばれることだけを想定しており、単体では起動しない。
3| # 他リポジトリからは `uses: <owner>/<repo>/.github/workflows/reusable-python-ci.yml@<ref>`
4| # として呼べる。
5| name: Reusable Python CI
6| 
7| on:
8|   workflow_call:
9|     inputs:
10|       python-versions:
11|         description: テストする Python バージョンの JSON 配列
12|         required: false
13|         default: '["3.12", "3.13"]'
14|         type: string
15| 
16| # permissions: このワークフローが GITHUB_TOKEN に許す操作。
17| # GITHUB_TOKEN はジョブごとに自動発行され、既定の権限はリポジトリ設定に依存する。
18| # ここで contents: read を明示することで、設定に関係なく「読むことしかできない
19| # トークン」に固定している。書き込みが必要なジョブが出てきたら、ワークフロー
20| # 全体ではなくそのジョブだけに permissions を足す（理由と実測は
21| # docs/stages/stage-06-security.md を参照）。
22| permissions:
23|   contents: read
24| 
25| env:
26|   ACTIONLINT_VERSION: "1.7.12"
27| 
28| jobs:
29|   static:
30|     name: Static Checks
31|     runs-on: ubuntu-latest
32|     timeout-minutes: 10
33|     steps:
34|       - name: リポジトリを取得する
35|         uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
36|         with:
37|           # 既定の浅い clone だとタグを取得しない。「解説の行番号引用を検証する」が
38|           # check_doc_citations.py 経由で git show <tag>:<path> を呼ぶため、
39|           # 全履歴とタグを取得しておく必要がある。
40|           fetch-depth: 0
41|           # このワークフローは checkout 後に git push をしないので、
42|           # 認証情報をワークスペースに残す必要が無い（zizmor: artipacked）。
43|           persist-credentials: false
44| 
45|       - name: Python 環境をセットアップする
46|         uses: ./.github/actions/setup-python-env
47|         with:
48|           python-version: "3.12"
49| 
50|       - name: フォーマットを確認する
51|         run: uv run ruff format --check .
52| 
53|       - name: lint を確認する
54|         run: uv run ruff check .
55| 
56|       - name: 型を確認する
57|         run: uv run mypy src tools
58| 
59|       - name: 解説の行番号引用を検証する
60|         run: uv run python tools/check_doc_citations.py docs/stages
61| 
62|       - name: ワークフローを actionlint で検査する
63|         run: |
64|           docker run --rm \
65|             --volume "${PWD}:/repo" \
66|             --workdir /repo \
67|             "rhysd/actionlint:${ACTIONLINT_VERSION}" -color
68| 
69|       # actionlint は「ワークフローとして壊れていないか」を見る。
70|       # zizmor は「危険な書き方をしていないか」を見る。目的が違うので両方入れる。
71|       - name: ワークフローをセキュリティ観点で検査する
72|         run: uv run zizmor .github/workflows/ .github/actions/
73| 
74|   test:
75|     name: Test (${{ matrix.os }} / Python ${{ matrix.python-version }})
76|     runs-on: ${{ matrix.os }}
77|     timeout-minutes: 10
78|     strategy:
79|       fail-fast: false
80|       matrix:
81|         os: [ubuntu-latest, windows-latest]
82|         # 入力は文字列なので、fromJSON で配列に戻してから matrix に渡す。
83|         python-version: ${{ fromJSON(inputs.python-versions) }}
84|         exclude:
85|           - os: windows-latest
86|             python-version: "3.12"
87|     steps:
88|       - name: リポジトリを取得する
89|         uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
90|         with:
91|           # このワークフローは checkout 後に git push をしないので、
92|           # 認証情報をワークスペースに残す必要が無い（zizmor: artipacked）。
93|           persist-credentials: false
94| 
95|       - name: Python 環境をセットアップする
96|         uses: ./.github/actions/setup-python-env
97|         with:
98|           python-version: ${{ matrix.python-version }}
99| 
100|       - name: テストを実行する
101|         run: uv run pytest -v --cov-report=html
102| 
103|       - name: カバレッジ HTML を artifact として保存する
104|         if: always()
105|         uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a  # v7.0.1
106|         with:
107|           name: coverage-html-${{ matrix.os }}-${{ matrix.python-version }}
108|           path: htmlcov/
109|           retention-days: 7
```

- **`permissions` の回収** — `GITHUB_TOKEN` は各ジョブの実行のたびに自動発行され、
  既定でどこまでの操作を許すかは**リポジトリ設定**（Settings → Actions → General →
  Workflow permissions）に依存します。`ci.yml` の19〜26行目、`reusable-python-ci.yml`
  の16〜23行目で `contents: read` を明示しているのは、このリポジトリ設定が将来
  変わっても（あるいは他の人がこのワークフローをコピーして別リポジトリの、既定が
  異なる設定の下で使っても）、「読むことしかできないトークン」であり続けることを
  ワークフロー自身に固定するためです。実際に `gh api repos/jane1210jane/githubactions-sample1/actions/permissions/workflow`
  を実行すると `{"default_workflow_permissions":"read", ...}` が返り、このリポジトリの
  既定はたまたま `read` でしたが、それは「設定を見なければ分からない」事実であり、
  `ci.yml` 19〜26行目のように明示すればこの確認自体が不要になります。実測として、
  `contents: read` のまま `gate` ジョブから `gh pr comment` を実行すると、
  次のエラーで失敗することを確認しました（run `30408370634`）。

  ```
  GraphQL: Resource not accessible by integration (addComment)
  ```

  `gate` ジョブ（`ci.yml` 59〜64行目）に job-scoped の
  `permissions: { contents: read, pull-requests: write }` を追加すると成功し、実際に
  PR にコメントが投稿されることを確認しました。**このとき `pull-requests: write` を
  ワークフローのトップレベルではなく `gate` ジョブだけに足したのには理由があります。**
  トップレベルに足すと `zizmor` の `excessive-permissions` が **`high` の severity**
  （`error`、終了コード `14`）として報告され、CI が落ちます。

  ```
  error[excessive-permissions]: overly broad permissions
    --> .github/workflows/ci.yml:23:3
     |
  23 |   pull-requests: write
     |   ^^^^^^^^^^^^^^^^^^^^ pull-requests: write is overly broad at the workflow level
     |
     = note: audit confidence → High
  ```

  「ワークフロー全体に効く権限」と「特定のジョブだけが必要とする権限」を区別し、
  後者はジョブ側の `permissions:` に書く、という設計そのものが「最小権限」の実践です。
  （`zizmor` の `error`/`warning` と終了コードの判定基準は、次の「`zizmor`」の項で
  まとめて扱います。）

- **`env:` 経由の回収** — `run:` の中に書いた `${{ }}` は、シェルが起動する**前**に
  文字列として展開されます。つまり展開後の文字列がそのままシェルのソースコードに
  なります。この危険性を実際のリポジトリで確かめるため、PR #21 のタイトルを一時的に
  `Stage 6: セキュリティ基礎"; echo INJECTED; #` に変更し（`gh api
  repos/.../issues/21/events` で `renamed` イベントとして記録されています）、直接
  埋め込む例と `env:` 経由の例を両方持つ実験ジョブを `ci.yml` に一時追加して push しました
  （commit `d56bb6a`）。直接埋め込んだ側の実際の生成スクリプトは次のようになり、

  ```
  echo "PR Title (direct): Stage 6: セキュリティ基礎"; echo INJECTED; #"
  ```

  `;` がコマンドの区切りとして解釈されるため、`echo "PR Title (direct): ..."` と
  `echo INJECTED` という**2つの独立したコマンド**として実行され、ログには

  ```
  PR Title (direct): Stage 6: セキュリティ基礎
  INJECTED
  ```

  の2行が出力されました。`INJECTED` は本来 `run:` の中に書いた覚えのない、PR タイトルの
  中身がそのままシェルの構文として解釈された結果です。一方 `env:` 経由の例
  （`hello.yml` の「挨拶する」ステップと同じ書き方）では、生成されたスクリプトは
  `echo "PR Title (env): ${PR_TITLE}"` のまま変わらず、`PR_TITLE` という環境変数の
  **値**としてタイトル文字列がまるごと渡されるため、出力は

  ```
  PR Title (env): Stage 6: セキュリティ基礎"; echo INJECTED; #
  ```

  の1行だけで、`;` や `#` はただの文字として印字されただけでした。`hello.yml` の
  「挨拶する」ステップが `GREETING_TARGET` を `env:` に置いているのは、
  `inputs.greeting_target`（利用者が自由に打ち込める値）が同じ経路を通らないようにする
  ためです。加えて、この実験の失敗の実際の原因は、CI が実行時に injection されたことを
  観測しただけでなく、**`actionlint` 自身が静的にこのパターンを検出して CI を
  落としたこと**でした。実際のログは次のとおりです。

  ```
  .github/workflows/ci.yml:110:43: "github.event.pull_request.title" is potentially
  untrusted. avoid using it directly in inline scripts. instead, pass it through an
  environment variable. [expression]
  ```

  つまり、もし `env:` を使い忘れて直接埋め込んでしまっても、`actionlint` がマージ前に
  食い止める安全網になっています（このリポジトリでは Stage 5 から `static` ジョブに
  組み込み済みです）。確認後、実験ジョブは `git revert` で完全に取り除きました
  （commit `cf0c7e1`、PR タイトルも元に戻し済み）。

- **`pull_request_target` の罠** — `pull_request` トリガーは、PR のマージコミット
  （`refs/pull/<番号>/merge`、base に head をマージした状態）の**コンテキストで動きます。**
  つまり、フォーク側が PR の中でワークフロー定義そのものを書き換えていれば、
  `pull_request` はその**書き換えられた定義**を実際に実行します。それでも事故が
  起きにくいのは、「base 側の定義が使われるから」ではなく、**発行される
  `GITHUB_TOKEN` が読み取り専用に近い権限しか持たず、`secrets` もフォークからの実行には
  渡らないから**です。`pull_request_target` はここが逆転します。
  `pull_request_target` で起動したワークフローは、**PR のマージコミットではなく
  base ブランチ側の定義**が、書き込み権限のあるトークンと `secrets` 付きで動きます。
  ここでうっかりフォーク側のコード
  （PR のコミット）をチェックアウトして実行すると、他人が書いたコードに書き込み権限つきの
  トークンを渡してしまうことになり、フォークからの悪意あるコードが `secrets` を盗んだり
  リポジトリに書き込んだりする典型的な事故パターンになります。**本教材では
  `pull_request_target` を使った実演はしません。** 危険な構成を実際に再現してみせる
  教材的価値より、事故が起きたときのリスクの方が明らかに上回るためです。ここでは
  「ベースブランチ側の定義が書き込みトークンつきで動く」という仕組みだけを理解して
  おき、実際に使う必要が生じたときは、フォークのコードをチェックアウトしない
  （PR のメタデータだけを読む）か、チェックアウトする場合でも `actions/checkout` の
  `ref` を明示的に検証してから使う、という原則を徹底してください。

- **SHA ピン留め** — `uses: actions/checkout@v7` のような**タグ参照は動きます**。
  `v7` というタグ自体が、そのリポジトリの管理者によって別のコミットを指すように
  書き換えられる可能性があり、書き換えられれば次に CI が動いたときから別のコードが
  実行されます。**SHA は動きません。** 40桁のコミット SHA はそのコミットの内容そのもの
  なので、`ci.yml` 37行目の `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1`
  のように SHA + バージョンコメントの形式にすることで、「今 CI で動いているコードは、
  確認したその時点のコードのままである」ことを保証します。同様のピン留めを
  `reusable-python-ci.yml` の35行目・89行目（`actions/checkout`）、105行目
  （`actions/upload-artifact`）にも適用しています。一方、`ci.yml` 54行目の
  `uses: ./.github/workflows/reusable-python-ci.yml` や、`reusable-python-ci.yml`
  46行目・96行目の `uses: ./.github/actions/setup-python-env` のような
  **ローカルパス参照（`./…`）はピン留めの対象外**です。これらはこのリポジトリ自身の
  内容を指しており、そもそも別のリビジョンを指定するための構文がありません
  （リポジトリを checkout した時点のコミットがそのまま使われます）。

- **Dependabot** — SHA でピン留めすると、更新は自動では入ってこなくなります。
  放置すると「動かないわけではないが、セキュリティ修正を含む更新が入らないまま古い」
  状態で固まってしまうため、`.github/dependabot.yml` を追加し、`github-actions`
  （`.github/workflows` と `.github/actions` の両方が対象）と `uv`（Python の依存）の
  両エコシステムを毎週チェックする設定にしました。`package-ecosystem: uv` が実際に
  受理される値であることは、push 後にリポジトリの check-runs に
  `.github/dependabot.yml`（Dependabot config file validation、`conclusion: success`）
  という検証チェックが自動生成されたことで確認しています。

- **`zizmor`** — `actionlint` は「ワークフローとして構文的に壊れていないか」を見ます
  （`reusable-python-ci.yml` 62〜67行目）。存在しないコンテキスト参照や無効な構文は
  指摘しますし、`github.event.pull_request.title` のような信頼できないコンテキストを
  `run:` に直接埋め込むパターンも `[expression]` ルールで検出します（前項「`env:`
  経由の回収」で実測したとおりです）。しかし、`permissions` が広すぎる・過去に
  ピン留めを忘れている・`actions/checkout` が認証情報を残したままになっている、
  といった**ワークフロー設計上のセキュリティ上の危険は対象外**です。`zizmor`
  （`reusable-python-ci.yml` 69〜72行目）はそこを埋め、こうした設計上の危険を
  パターンとして検出します。導入時にローカルで `uv run zizmor
  .github/workflows/ .github/actions/` を実行したところ、`actions/checkout` を使う
  3箇所（当時の `ci.yml` の `meta` ジョブ、`reusable-python-ci.yml` の `static`
  ジョブ・`test` ジョブ）すべてで次の指摘（`artipacked`）が出ました。

  ```
  4 findings (1 suppressed, 3 unsafe fixes): 0 informational, 0 low, 3 medium, 0 high
  ```

  `actions/checkout` は既定で、チェックアウト後もワークスペースに認証情報
  （`git` の `http.extraheader` など）を残します。このリポジトリのワークフローは
  checkout 後に `git push` をしないため、その認証情報を残しておく必要がありません。
  抑制コメント（`# zizmor: ignore`）は一切使わず、`ci.yml` 38〜41行目、
  `reusable-python-ci.yml` 36〜43行目・90〜93行目のように、各 `actions/checkout` に
  `persist-credentials: false` を追加してコード側で直しました。修正後の再実行結果は
  `No findings to report. Good job! (1 suppressed)` で、終了コードは `0` でした。

  **`zizmor` の `error`/`warning` と終了コードは `severity`（`informational` /
  `low` / `medium` / `high`）で決まり、`confidence`（`low` / `medium` / `high`、
  「どれだけ確からしいか」）とは独立した軸です。** severity が `high` の指摘は
  `error` として終了コード `14`、`medium` の指摘は `warning` として終了コード
  `13`（`low` は `12`、`informational` は `11`、指摘が無ければ `0`）になります。
  実際に手元で確認したところ、`pull_request_target` トリガーを検出する
  `dangerous-triggers` は `audit confidence → Medium` であるにもかかわらず
  severity は `high`（`error`、終了コード `14`）でした。逆に、この `artipacked`
  （`persist-credentials` 未設定）は `audit confidence → Low` でも severity は
  `medium`（`warning`、終了コード `13`）です。`--min-severity` と `--min-confidence`
  はそれぞれ独立にフィルタするオプションで、どちらか一方だけで「これ以上の
  確からしさ・深刻さのものだけを見る」という絞り込みができます。

- **`persist-credentials: false`**（前項で導入） — `ci.yml` 38〜41行目、
  `reusable-python-ci.yml` 36〜43行目・90〜93行目にあるとおり、`actions/checkout` の
  直後の `with:` に置きます。これが無いと、checkout した認証情報がワークスペース内の
  git 設定に残り続け、そのジョブの後続ステップ（例えば `docker run` で任意のイメージを
  実行する actionlint のステップなど）から、意図せずその認証情報にアクセスできる状態に
  なります。checkout 後に `git push` を行わないジョブでは、そもそも認証情報を
  残しておく理由がありません。

## 6. つまずきポイント

- SHA ピン留めしたまま Dependabot を入れないと、更新の検知手段が無いまま
  古いバージョンで固まる。ピン留めと Dependabot は必ずセットで導入する。
- `permissions` をトップレベルに書くと、**ワークフロー内のすべてのジョブ**に効く。
  特定のジョブだけに権限を足したいときは、そのジョブの `permissions:` に書く。
  `ci.yml` の `gate` ジョブ（59〜64行目）に `pull-requests: write` を足す実験では、
  トップレベルに足すと `zizmor` の `excessive-permissions` に拒否され、ジョブレベルに
  限定することで解消しました（前節参照）。**さらに、`gate` ジョブには
  `actions/checkout` が一度も無いことに注意が必要です。** `gh` CLI のような
  ツールがリポジトリを自動判定するには `--repo` フラグか `GH_REPO` 環境変数か
  `git remote` のいずれかが要り、checkout の無いジョブでは最後の手段が無いため、
  `gh` を使う実験ステップには `env: GH_REPO: ${{ github.repository }}` を明示する
  必要があります。これを忘れると `fatal: not a git repository (or any of the
  parent directories): .git` という、`permissions` とは無関係の別のエラーになり、
  「権限が原因で失敗した」と誤診してしまいます。
- 既定の `GITHUB_TOKEN` 権限はリポジトリ設定（`gh api repos/<owner>/<repo>/actions/permissions/workflow`
  の `default_workflow_permissions`）に依存する。ワークフローに `permissions:` を
  明示的に書けば、リポジトリ設定が何であっても、書いたとおりの権限に固定できる。
  このリポジトリで実際に `permissions:` ブロックをまるごと取り除いて確かめたところ、
  `Metadata` ジョブに発行されたトークンの権限が `Contents: read` / `Metadata: read`
  に加えて `Packages: read` まで含む形に**広がった**ことをジョブログの
  `GITHUB_TOKEN Permissions` セクションで確認しました。CI 自体はこのリポジトリの
  既定が `read` だったためこの時点では壊れませんでしたが、`zizmor` は
  `excessive-permissions`（`default permissions used due to no permissions: block`）
  を4件報告し、「明示していない = 何が渡っているか静的に読み取れない」こと自体を
  リスクとして扱っていました。実際の出力は次のとおりです（確認後は revert 済み）。

  ```
  warning[excessive-permissions]: overly broad permissions
   --> .github/workflows/ci.yml:20:3
      default permissions used due to no permissions: block
  5 findings (1 suppressed): 0 informational, 0 low, 4 medium, 0 high
  ```

- `zizmor` の指摘を `# zizmor: ignore` で黙らせるのは、検査を入れた意味そのものを
  失わせる。このリポジトリでは一度も使っていない（`grep -rn "zizmor: ignore"
  .github/` で確認済み、ヒット無し）。指摘が出たらコード側を直す。
- 手順C で採取した実際の権限エラーの文言は次のとおりで、これは
  `permissions: contents: read` のときに `GITHUB_TOKEN` で PR にコメントしようと
  すると起こります（前節参照）。

  ```
  GraphQL: Resource not accessible by integration (addComment)
  ```

## 7. 演習課題

以下の3問は [docs/stages/answers/stage-06.md](answers/stage-06.md) に解答があります。
まず自分で予想してから答えを見てください。

1. **問1**: `run:` に `${{ github.event.pull_request.title }}` を直接書いたワークフローと、
   `env:` 経由にしたワークフローで、タイトルに `"; echo INJECTED; #` を含む PR を作ると
   どうなるか。自分のリポジトリで安全に試せるので、実際に試して結果を記録する。
2. **問2**: `zizmor` の指摘を1つ意図的に再導入し（例: 1つの `uses:` をタグ参照に
   戻す）、CI が落ちることを確認する。落ちたときの `zizmor` の出力を記録する。
   確認後は戻す。
3. **問3**: `permissions` をトップレベルから削除すると何が起きるか予想し、確かめる。
   既定の権限がリポジトリ設定に依存することを、`gh api
   repos/{owner}/{repo}/actions/permissions/workflow` で確認する。

## 8. 実務への持ち込みメモ

すでに動いている既存リポジトリにこのステージの内容を適用するときは、いきなり
全部を一度にやろうとしないでください。まず `permissions:` を明示的に書くところから
始めます。ここはリポジトリ設定に依存しない振る舞いを取り戻すだけの変更で、
既存のワークフローの動作を壊すリスクが最も低く、しかも効果（既定に頼らない）が
すぐに出ます。次に SHA ピン留めをするときは、**社内やサードパーティの action から
順に**進めてください。すべての `uses:` を一度に SHA へ置き換えると差分が非常に
大きくなり、レビューする側が「本当に同じコードを指しているか」を1つ1つ検証しきれず、
レビューが通らない（あるいは形だけ通ってしまう）事態を招きます。Dependabot を
先に、あるいは同時に入れておかないと、ピン留めしたことで更新の検知手段を失った
まま古くなる、という本末転倒にもなるので、ピン留めと Dependabot は必ずセットで
進めてください。
