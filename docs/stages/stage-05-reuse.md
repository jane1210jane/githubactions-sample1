# Stage 5: 再利用と構造化

## 1. このステージのゴール

重複した「checkout → setup-uv → uv sync」の3ステップを自作の composite action にまとめ、
CI 本体（静的検査とテスト）を `workflow_call` の reusable workflow として切り出します。
到達点は、`ci.yml` を他リポジトリへ配る形の**出発点**にすることです（他リポジトリへ
そのまま配れる状態にはまだなっていません。理由は「つまずきポイント」で扱います）。

## 2. 前提

- `stage-04` が完了していること。`meta` / `static` / `test` / `gate` の4ジョブ構成で CI が動き、
  カバレッジ閾値・mypy・ステップサマリが `static` / `gate` に組み込まれている状態です。

## 3. なぜ必要か

`stage-03` でジョブを `static` と `test` に分けた結果、「uv セットアップ → 依存インストール」
という同じ2ステップが `static` / `test` の2箇所に重複していました（`stage-04` で増えた
`meta` は Python 環境を使わないため、この2ステップを持っていません。手順Aの
「`meta` ジョブは Python 環境を使わないため変更していません」も参照してください）。
この重複には実害があります。たとえば `uv` のバージョンを固定したくなったとき、
2箇所のうち1箇所だけを直して残り1箇所を直し忘れる、という事故が起こり得ます。
コピーされたステップは、コピーした瞬間から同期が取れなくなる運命にあります。

もう1つの動機は、このリポジトリの外にあります。会社で複数のリポジトリを持っていると、
「同じ品質基準の CI を全部に配りたい」という要求が必ず出てきます。しかし `ci.yml` を
リポジトリ間でコピーして配ると、それぞれが独立したファイルになった瞬間から、
一方だけ直して他方に反映されない状態が始まります。このステージでは、(1) 重複したステップを
composite action にまとめ、(2) CI の本体を reusable workflow として切り出すことで、
「1箇所を直せば全部に効く」形を作ります。

## 4. 手順

以下は実際に行った手順です。

### 手順A: composite action を自作する

`.github/actions/setup-python-env/action.yml` を新規作成しました。入力は
`python-version`（必須）の1つだけで、`astral-sh/setup-uv@v7` に続けて `uv sync --locked` を
実行します。**checkout はこの action に含めていません**（理由は次節）。続けて `ci.yml` の
`static` ジョブと `test` ジョブの、checkout 直後にあった「uv と Python をセットアップする」
「依存関係をインストールする」の2ステップを、`uses: ./.github/actions/setup-python-env` の
1ステップに置き換えました。`meta` ジョブは Python 環境を使わないため変更していません。

commit `e5800f5` を push した結果、PR #13 上で実行 ID `30284665675` がトリガーされ、
全ジョブが green になりました（`Metadata` / `Static Checks` / `Test (ubuntu-latest / Python
3.12)` / `Test (ubuntu-latest / Python 3.13)` / `Test (windows-latest / Python 3.13)` /
`Lint & Test` の6件）。この時点では `static` と `test` はまだ `ci.yml` の中の通常ジョブで、
Checks 名は composite action を導入する前と1件も変わっていません。純粋なリファクタリングとして
成立していることを、この「名前が変わらない」という事実で確認しました。

### 手順B: reusable workflow に切り出す

`.github/workflows/reusable-python-ci.yml` を新規作成し、`on: workflow_call` を持つ
reusable workflow として、`static` ジョブと `test` ジョブをそのまま移しました。
入力 `python-versions`（JSON 配列を表す**文字列**、既定値 `'["3.12", "3.13"]'`）を宣言し、
`test` ジョブの `matrix.python-version` は `fromJSON(inputs.python-versions)` で配列に戻して
渡しています。続けて `ci.yml` を、`meta` ジョブと、`checks`（`uses:
./.github/workflows/reusable-python-ci.yml` で呼び出すだけ）、`gate`（`needs: [meta,
checks]`）の3ジョブだけの薄い呼び出し元に書き換えました。

commit `271a130` を push した結果、実行 ID `30285144196` で全ジョブが成功しました。
このとき Checks の名前が変わったことを実測しました（詳しくは次節）。続けて、
`workflow_call` の入力が実際に効くことを確認するため、`checks:` に一時的に
`with: { python-versions: '["3.13"]' }` を渡す実験を行いました（commit `6c35ef0`、
実行 ID `30285234700`）。結果、`test` の matrix が3レグから2レグ（`Python 3.13` の
`ubuntu-latest` と `windows-latest` のみ）に縮み、`Checks / Test (ubuntu-latest / Python
3.12)` が Checks 一覧から消えました。確認後 `git revert --no-edit HEAD` で戻し
（commit `6f47290`、実行 ID `30285311474`）、3レグ構成に復元されたことを確認しています。

その後のレビューで、`reusable-python-ci.yml` の `permissions:` にも `ci.yml` と同じ
Stage 6 の伏線コメントを置くべきという指摘があり、2行のコメントを追加しました
（commit `1cc2051`、実行 ID `30285930412`）。以降の行番号は、**このステージ完了時点
（タグ `stage-05`）の3ファイル**を転記したブロックの行番号を指します。リポジトリの
実ファイルを開いて数える必要はありません。ブロックが3つあるため、引用はすべて
「`ファイル名` の N行目」の形式で、どのファイルを指しているかを明記します。

`action.yml`（`.github/actions/setup-python-env/action.yml`）:

<!-- transcript: .github/actions/setup-python-env/action.yml @ stage-05 -->
```
 1| # 自作の composite action。
 2| # 「uv セットアップ → 依存インストール」の2ステップが
 3| # static / test で重複していたので、1つの uses: にまとめる。
 4| #
 5| # checkout はこの action に含めない。composite action は呼び出し元の
 6| # ワークスペースでそのまま動くため、どのリポジトリを取得するかは
 7| # 呼び出し側が決めるべきだから。
 8| name: Python 環境をセットアップする
 9| description: uv と指定バージョンの Python を用意し、ロックファイルどおりに依存をインストールする
10| 
11| inputs:
12|   python-version:
13|     description: 使用する Python のバージョン
14|     required: true
15| 
16| runs:
17|   using: composite
18|   steps:
19|     - name: uv と Python をセットアップする
20|       uses: astral-sh/setup-uv@v7
21|       with:
22|         python-version: ${{ inputs.python-version }}
23| 
24|     # composite action の run: には shell の指定が必須。
25|     # ワークフローの run: と違って既定値が無い。
26|     - name: 依存関係をインストールする
27|       run: uv sync --locked
28|       shell: bash
```

`ci.yml`（`.github/workflows/ci.yml`）:

<!-- transcript: .github/workflows/ci.yml @ stage-05 -->
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
20| # 最小権限にしておく。なぜ必要かは Stage 6 で回収する。
21| permissions:
22|   contents: read
23| 
24| jobs:
25|   meta:
26|     name: Metadata
27|     runs-on: ubuntu-latest
28|     timeout-minutes: 5
29|     outputs:
30|       version: ${{ steps.read.outputs.version }}
31|     steps:
32|       - name: リポジトリを取得する
33|         uses: actions/checkout@v7
34| 
35|       - name: pyproject.toml からバージョンを読む
36|         id: read
37|         run: |
38|           version=$(grep -m1 '^version = ' pyproject.toml | cut -d '"' -f 2)
39|           echo "読み取ったバージョン: ${version}"
40|           echo "version=${version}" >> "${GITHUB_OUTPUT}"
41| 
42|   # 再利用可能ワークフローの呼び出し。同じリポジトリ内なので ./ で参照できる。
43|   # jobs.<id>.uses を使うジョブには steps を書けない。呼び出しそのものがジョブになる。
44|   checks:
45|     name: Checks
46|     uses: ./.github/workflows/reusable-python-ci.yml
47| 
48|   # 集約ゲート。ruleset が必須チェックとして見ているのはこのジョブの name。
49|   # 呼び出し先のジョブ名は `Checks / Static Checks` のように変わるが、
50|   # この名前さえ保てば ruleset を触らずに済む。
51|   gate:
52|     name: Lint & Test
53|     runs-on: ubuntu-latest
54|     needs: [meta, checks]
55|     if: always()
56|     timeout-minutes: 5
57|     steps:
58|       - name: 結果をステップサマリに書く
59|         env:
60|           APP_VERSION: ${{ needs.meta.outputs.version }}
61|           CHECKS_RESULT: ${{ needs.checks.result }}
62|         run: |
63|           {
64|             echo "## CI 結果"
65|             echo ""
66|             echo "| 項目 | 値 |"
67|             echo "| --- | --- |"
68|             echo "| バージョン | ${APP_VERSION} |"
69|             echo "| 検査とテスト | ${CHECKS_RESULT} |"
70|           } >> "${GITHUB_STEP_SUMMARY}"
71| 
72|       - name: PR 向けの案内を出す
73|         if: github.event_name == 'pull_request'
74|         run: |
75|           {
76|             echo ""
77|             echo "カバレッジの詳細は Artifacts の \`coverage-html-*\` を開いてください。"
78|           } >> "${GITHUB_STEP_SUMMARY}"
79| 
80|       - name: 依存ジョブの結果を判定する
81|         env:
82|           DEPENDENCY_RESULTS: ${{ join(needs.*.result, ' ') }}
83|         run: |
84|           echo "依存ジョブの結果: ${DEPENDENCY_RESULTS}"
85|           read -ra results <<< "${DEPENDENCY_RESULTS}"
86|           for result in "${results[@]}"; do
87|             if [ "${result}" != "success" ]; then
88|               echo "success ではない依存ジョブがあります"
89|               exit 1
90|             fi
91|           done
92|           echo "すべての依存ジョブが success です"
```

`reusable-python-ci.yml`（`.github/workflows/reusable-python-ci.yml`）:

<!-- transcript: .github/workflows/reusable-python-ci.yml @ stage-05 -->
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
17| # 最小権限にしておく。なぜ必要かは Stage 6 で回収する。
18| permissions:
19|   contents: read
20| 
21| env:
22|   ACTIONLINT_VERSION: "1.7.12"
23| 
24| jobs:
25|   static:
26|     name: Static Checks
27|     runs-on: ubuntu-latest
28|     timeout-minutes: 10
29|     steps:
30|       - name: リポジトリを取得する
31|         uses: actions/checkout@v7
32| 
33|       - name: Python 環境をセットアップする
34|         uses: ./.github/actions/setup-python-env
35|         with:
36|           python-version: "3.12"
37| 
38|       - name: フォーマットを確認する
39|         run: uv run ruff format --check .
40| 
41|       - name: lint を確認する
42|         run: uv run ruff check .
43| 
44|       - name: 型を確認する
45|         run: uv run mypy src tools
46| 
47|       - name: 解説の行番号引用を検証する
48|         run: uv run python tools/check_doc_citations.py docs/stages
49| 
50|       - name: ワークフローを actionlint で検査する
51|         run: |
52|           docker run --rm \
53|             --volume "${PWD}:/repo" \
54|             --workdir /repo \
55|             "rhysd/actionlint:${ACTIONLINT_VERSION}" -color
56| 
57|   test:
58|     name: Test (${{ matrix.os }} / Python ${{ matrix.python-version }})
59|     runs-on: ${{ matrix.os }}
60|     timeout-minutes: 10
61|     strategy:
62|       fail-fast: false
63|       matrix:
64|         os: [ubuntu-latest, windows-latest]
65|         # 入力は文字列なので、fromJSON で配列に戻してから matrix に渡す。
66|         python-version: ${{ fromJSON(inputs.python-versions) }}
67|         exclude:
68|           - os: windows-latest
69|             python-version: "3.12"
70|     steps:
71|       - name: リポジトリを取得する
72|         uses: actions/checkout@v7
73| 
74|       - name: Python 環境をセットアップする
75|         uses: ./.github/actions/setup-python-env
76|         with:
77|           python-version: ${{ matrix.python-version }}
78| 
79|       - name: テストを実行する
80|         run: uv run pytest -v --cov-report=html
81| 
82|       - name: カバレッジ HTML を artifact として保存する
83|         if: always()
84|         uses: actions/upload-artifact@v7
85|         with:
86|           name: coverage-html-${{ matrix.os }}-${{ matrix.python-version }}
87|           path: htmlcov/
88|           retention-days: 7
```

## 5. 何が変わったか

- **composite action と reusable workflow の違い**: composite action（`action.yml`
  1〜28行目）は**ステップの塊**です。`runs.using: composite`（`action.yml` 17行目）で
  始まり、呼び出す側のジョブの中に、あたかも1つのステップであるかのように埋め込まれます
  （`reusable-python-ci.yml` 33〜36行目、74〜77行目）。それ自体は `runs-on` を持たず、
  呼び出し元のジョブが動いているランナーの上でそのまま実行されます。一方 reusable
  workflow（`reusable-python-ci.yml` 全体）は**ジョブの塊**で、`workflow_call`
  （`reusable-python-ci.yml` 7〜14行目）を `on:` に持つワークフロー自体です。呼び出し側では `jobs.<id>.uses`
  （`ci.yml` 46行目）としてジョブそのものになり、`static` / `test` という**独立したジョブ**
  として、それぞれ自分の `runs-on`（`reusable-python-ci.yml` 27行目、59行目）で
  ランナーを選びます。ランナー（実行環境）を指定できるのは reusable workflow の
  ジョブ側だけで、composite action の中には `runs-on` という概念自体がありません。
- **`runs.using: composite`（`action.yml` 17行目）と、`run:` に `shell:`（`action.yml` 28行目）が
  必須であること**: 通常のワークフローの `run:` ステップは、`runs-on` で決まったランナーの
  既定シェル（Linux/macOS は `bash`、Windows は `pwsh`）を暗黙に使います。composite action
  にはこの既定がありません。同じ composite action が Linux から呼ばれるか Windows から
  呼ばれるかは、呼び出され方次第で変わるため、GitHub 側では既定シェルを決めようがなく、
  `run:` を書くたびに `shell:` を明示することが**必須**になっています。
- **composite action に checkout を含めなかった理由**: composite action は
  「呼び出し元がすでに checkout 済みのワークスペース」の上でそのまま動きます
  （`uses: ./...` というローカルパス参照が成立するのも、リポジトリがすでに手元にある
  前提だからです）。もし action 自身が checkout をやり直すと、呼び出し元がすでに
  チェックアウトしていた特定のコミット・ブランチと、action が checkout し直す対象
  （既定では単に現在の ref）がずれる余地が生まれます。「どのリポジトリのどの状態を
  使うか」は呼び出し側の責任にする、という役割分担のために、`action.yml`
  1〜28行目には checkout のステップを含めていません。
- **`jobs.<id>.uses` を使うジョブには `steps` を書けないこと**: `checks:`
  （`ci.yml` 44〜46行目）は `uses:` だけを持ち、`steps:` も `runs-on:` も書いていません。
  `jobs.<id>.uses` は「このジョブの中身は、呼び出し先のワークフローが定義するジョブ群
  そのものである」という宣言であり、呼び出し元でさらに `steps:` を並べる余地はありません。
- **`workflow_call` の `inputs` と `fromJSON()`**: `workflow_call` の `inputs`
  （`reusable-python-ci.yml` 9〜14行目）に**配列型は存在しません**。`python-versions`
  は `type: string`（`reusable-python-ci.yml` 14行目）として、JSON 配列を表す**文字列** `'["3.12", "3.13"]'`
  （`reusable-python-ci.yml` 13行目）を受け取ります。`test` ジョブの `matrix.python-version`
  （`reusable-python-ci.yml` 66行目）では、この文字列を `fromJSON(inputs.python-versions)` で実際の配列に
  変換してから `matrix:` に渡しています。matrix はここでもとの `[ubuntu-latest,
  windows-latest]`（`reusable-python-ci.yml` 64行目）との直積を取り、`exclude`（`reusable-python-ci.yml` 67〜69行目）で
  `windows-latest` × `3.12` を除いた組み合わせが実際に走ります。
- **呼び出すと Checks 名が変わること**: `static` / `test` が `ci.yml` の中の通常ジョブ
  だったとき（手順Aの時点）、Checks 名は `Static Checks` / `Test (ubuntu-latest /
  Python 3.12)` のようにジョブの `name:` そのものでした。`reusable-python-ci.yml`
  に切り出して `checks:`（`ci.yml` 44〜46行目、`name: Checks`）から呼ぶようにした後
  （手順Bの commit `271a130`、実行 ID `30285144196`）、`gh pr checks 13` で観測した
  Checks 名は `Checks / Static Checks`、`Checks / Test (ubuntu-latest / Python
  3.12)` のように、**`<呼び出し側ジョブの name> / <呼び出し先ジョブの name>`**
  という形に変わっていました。一方 `Metadata`（`meta`、`ci.yml` 25〜26行目）と
  `Lint & Test`（`gate`、`ci.yml` 51〜52行目）は呼び出し元にそのまま残るジョブなので、
  名前は変わっていません。だからこそ、ruleset が必須チェックとして要求している
  `Lint & Test` を持つ `gate` を呼び出し元の `ci.yml` に残し、`static` / `test`
  だけを reusable workflow 側に移しています。もし `gate` も向こう側に移していたら、
  必須チェック名そのものが呼び出し先の名前に変わり、ruleset の要求する名前が
  二度と報告されなくなっていたはずです（演習課題の問2で扱います）。
- **他リポジトリから呼ぶときの書式**: このリポジトリ内からの参照はローカルパス
  `uses: ./.github/workflows/reusable-python-ci.yml`（`ci.yml` 46行目）ですが、
  別のリポジトリからは `uses: <owner>/<repo>/.github/workflows/
  reusable-python-ci.yml@<ref>` の形式で参照します（`reusable-python-ci.yml`
  3〜4行目のコメントに記載）。`<ref>` にはブランチ名・タグ・コミット SHA を指定できます。

## 6. つまずきポイント

- composite action の `run:` に `shell:` を書き忘れると `Required property is missing:
  shell` で落ちる（`action.yml` 28行目）。実際に `shell: bash` を1行削って push すると、
  ワークフロー全体の構文エラーにはならず（`Metadata` ジョブは checkout しかしないため
  最後まで成功しました）、composite action を使う**各ジョブが「Python 環境をセットアップする」
  ステップに到達した時点で**、`GitHub.DistributedTask.ObjectTemplating.
  TemplateValidationException: The template is not valid. .../action.yml (Line: 26,
  Col: 7): Required property is missing: shell` という例外でその action の読み込みに
  失敗し、そのジョブ全体が failure になることを実測しました（詳しくは演習課題の問1）。
- **composite action の `run:` に `shell: bash` を書いたことで、Windows ランナーでの
  シェルが変わっている。** `test (windows-latest / Python 3.13)` は本来 `pwsh`
  （PowerShell Core、Windows ランナーの既定シェル）でステップを実行しますが、
  `uv sync --locked` を実行する composite action のステップ（`action.yml` 26〜28行目）
  だけは `shell: bash`（`action.yml` 28行目）を明示しているため、Windows 上でも Git Bash で
  実行されます。これは composite action に既定シェルという概念が無い（前節参照）以上
  避けようがなく、今のところ `uv sync --locked` の結果に観測できる違いはありませんが、
  「リファクタリングしただけのはずなのに、実行環境の一部（シェル）が静かに変わっている」
  例として意識しておく必要があります。シェル依存の構文（例えばパスの区切り文字や
  環境変数展開の書式）をこのステップに足すときは、Windows でも Git Bash 前提で
  書かなければなりません。
- `uses: ./...` の意味は、**どの階層に書くか**で変わります。**ステップの `uses: ./...`
  （composite action、`reusable-python-ci.yml` 33〜36行目・74〜77行目）は、呼び出し元で
  checkout していないと action が見つからずに失敗します。** composite action は
  「呼び出し元のワークスペースにすでにあるファイル」として読み込まれるため、
  `actions/checkout@v7` より前に `uses: ./.github/actions/setup-python-env` を
  置くと失敗します。**一方、ジョブの `jobs.<id>.uses:`（reusable workflow、`ci.yml`
  44〜46行目の `checks:`）は checkout を必要としません。** `jobs.<id>.uses` は
  GitHub がリポジトリ側でワークフロー参照を解決する仕組みで、ランナーのファイル
  システムを経由しないためです。実際 `checks:`（`ci.yml` 44〜46行目）には `steps:` も
  checkout も無く、それでも `./.github/workflows/reusable-python-ci.yml` の呼び出しは
  成立しています。「`uses: ./...` は checkout が要る」という一般則ではなく、
  ステップレベル（composite action）にだけ当てはまる制約です。
- reusable workflow を呼ぶと Checks 名が変わる。**必須チェックにしている名前が
  呼び出し先にあると、ゲートが外れる。** 前節で実測したとおり、`static` は
  `Checks / Static Checks` に変わります。ruleset が `Static Checks` という名前そのものを
  必須にしていたら、その名前は二度と報告されず、PR が永久に「Waiting for status to be
  reported」のまま止まります。
- reusable workflow は呼び出し元の `env:` を引き継がない。必要な値は `inputs`
  で渡す。`reusable-python-ci.yml` の `ACTIONLINT_VERSION`（`reusable-python-ci.yml` 22行目）は、`ci.yml`
  側の `env:` とは無関係な、reusable workflow 自身が持つ独立した `env:`
  （`reusable-python-ci.yml` 21〜22行目）です。
- `workflow_call` の `inputs` に配列型は無い。JSON 文字列で渡して `fromJSON()`
  する。素朴に `python-versions: ["3.12", "3.13"]` のような配列リテラルを `inputs`
  に渡そうとすると、`type: string`（`reusable-python-ci.yml` 14行目）としか
  宣言できないため、YAML の配列ではなく**配列を表す文字列**として渡す必要があります。
- 他リポジトリの reusable workflow を `@main` で参照すると、向こうの変更が
  予告なく自分の CI を壊す。タグかコミットで固定する。
- **`reusable-python-ci.yml` を他リポジトリから呼び出しても、そのままでは動きません。**
  `static` / `test` ジョブ（`reusable-python-ci.yml` 33〜36行目・74〜77行目）は
  `uses: ./.github/actions/setup-python-env` というローカルパス参照で composite action
  を呼んでいます。他リポジトリから `uses: jane1210jane/githubactions-sample1/
  .github/workflows/reusable-python-ci.yml@<ref>` として呼んだ場合でも、その中の
  `actions/checkout@v7`（`reusable-python-ci.yml` 31行目・72行目）はあくまで**呼び出し元
  （caller）のリポジトリ**を取得するため、`./.github/actions/setup-python-env` は
  呼び出し元の作業ツリーの中で探され、`Can't find 'action.yml'` のようなエラーで
  失敗します（呼び出し元が自分のリポジトリに同じパスで action のコピーを
  持っていない限り）。加えて `mypy src tools` や `check_doc_citations.py docs/stages`
  （`reusable-python-ci.yml` 45行目・48行目）は、このリポジトリのディレクトリ構成に
  決め打ちしたコマンドです。他リポジトリへ配りたい場合の選択肢は主に3つです。
  (1) composite action の呼び出しをやめてステップをインライン展開する、
  (2) composite action を専用リポジトリに切り出してタグ付きで公開し、呼び出し元
  ワークフローからそのタグを参照する、(3) 呼び出し側リポジトリに、この action と
  同じ相対パスでコピーを用意してもらう。いずれも「1リポジトリで動いている
  reusable workflow」から「他リポジトリへ配れる reusable workflow」への
  追加作業が必要で、まだそこには到達していません。

## 7. 演習課題

以下の3問は [docs/stages/answers/stage-05.md](answers/stage-05.md) に解答があります。
まず自分で予想してから答えを見てください。

1. **問1**: composite action（`action.yml`）の `run:` から `shell: bash`
   （`action.yml` 28行目）を消すとどうなるか確かめる。確認後は戻す。
2. **問2**: `gate` ジョブを reusable workflow 側へ移すと何が起きるか予想し、
   **実行はせずに**説明する。
3. **問3**: `python-versions`（`reusable-python-ci.yml` 13行目）の既定値を
   `'["3.12"]'` に変え、呼び出し側で何も指定せずに実行する。確認後は戻す。

## 8. 実務への持ち込みメモ

共通 CI を複数リポジトリへ配りたくなったときは、いきなり reusable workflow として
切り出すのではなく、**まず1つのリポジトリで使い込んでから**切り出してください。
使う前に抽象化すると、「どの値を `inputs` として外に出すべきか」がまだ分からない
段階で設計してしまい、後から `inputs` を足したり構造を組み替えたりする手戻りが
発生します。このステージでも、`python-versions` という1つの `inputs` を持つ形に
たどり着けたのは、`ci.yml` を1つのリポジトリの中で `static` / `test` /
`gate` に分けて実際に運用したからです。切り出した reusable workflow を他リポジトリ
から参照するときは、`@main` のような可変の ref ではなく**タグで参照**し、
更新は「向こうのタグを上げて、こちらも意図的に追従する」という能動的な操作として
行ってください。
