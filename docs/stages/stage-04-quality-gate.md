# Stage 4: 品質ゲート

## 1. このステージのゴール

品質が落ちたら CI が落ちる状態にし、その結果を実行画面で読めるようにします。
「数字は表示されているが誰も見ていない」状態を終わらせ、落ちた理由と現在の状態を
Actions の実行画面だけで把握できるようにするのがこのステージの到達点です。

## 2. 前提

- `stage-03` が完了していること。`static` / `test` / `gate` の3層構成で CI が動き、
  actionlint と行番号引用検査が `static` に組み込まれている状態です。

## 3. なぜ必要か

`stage-01` の時点から、テストは `--cov-report=term-missing` でカバレッジを**表示**してきました。
しかし表示するだけの数字には強制力がありません。カバレッジが 98% から 70% に落ちても、
CI は変わらず緑のままです。誰かが Actions のログを開いてカバレッジの行を目で追わない限り、
劣化には気づけません。これは「レビューで見ればわかる」に頼った運用であり、
見落としが起きた瞬間にその前提は崩れます。

もう1つの問題は、`stage-03` で matrix を導入した結果として生まれました。ジョブが
`static` / `Test (ubuntu-latest / Python 3.12)` / `Test (ubuntu-latest / Python 3.13)` /
`Test (windows-latest / Python 3.13)` / `gate` の5つに増え、実行画面のジョブ一覧を見ても、
「今回の実行全体としてどういう結果だったか」を一目で把握しにくくなりました。個々のジョブの
成否は追えても、集約した情報（バージョン、各層の結果）がどこにもまとまっていません。

このステージでは、(1) カバレッジに実際に効く閾値を設定してゲート化する、(2) 型チェックを
CI に加えてより早い段階で問題を検出する、(3) ジョブ間で値を受け渡す `outputs` の使い方を
実例で学ぶ、(4) 実行結果を Markdown の要約として実行画面に表示する、という4つを組み合わせて
これらの問題に対処します。

## 4. 手順

以下は Task 6・7 で実際に行った手順です（このドキュメントでは Task 番号ではなく
実施内容で示します）。

### 手順A: mypy を導入する

`pyproject.toml` の `[dependency-groups].dev` に `mypy>=1.11` を追加し、`uv sync` で
ロックファイルを更新しました。続けて `[tool.mypy]` セクションを追加し、
`python_version = "3.12"`、`disallow_untyped_defs = true`、`warn_unused_ignores = true`、
`warn_return_any = true`、`tests` ディレクトリを対象外にする `exclude = ["^tests/"]` を
設定しました。この状態で `uv run mypy src tools` を実行したところ、初回から

```
Success: no issues found in 4 source files
```

指摘は0件でした。既存のコードがすでに型注釈を完備していたためで、注釈を追加する作業は
発生していません。これは「型チェックを後から導入するほど大きな手直しが要る」という
一般論に対する例外というより、このプロジェクトの規模がまだ小さく、最初から丁寧に
書かれていたことの結果です。

### 手順B: カバレッジ閾値を有効化し、実際に効くことを確認する

`pyproject.toml` の `addopts` に `--cov-fail-under=80` を追加しました。値がどこにあっても
動作は同じに見えるため、本当に効くかを確認する目的で、一時的に `100` にして実行しました。

```
$ sed -i 's/--cov-fail-under=80/--cov-fail-under=100/' pyproject.toml
$ uv run pytest -q; echo "EXIT=$?"
...
ERROR: Coverage failure: total of 98 is less than fail-under=100
...
FAIL Required test coverage of 100% not reached. Total coverage: 98.26%
28 passed in 0.15s
EXIT=1
```

期待どおり `EXIT=1` で落ちました。`80` に戻すと `EXIT=0` に戻ることも確認し、
`git diff` でコミット直前の内容が `80` のままであることを確かめてからコミットしています。

### 手順C: `static` ジョブに mypy ステップを追加する

`ci.yml` の `static` ジョブに、「lint を確認する」の直後として「型を確認する」
（`uv run mypy src tools`）を追加しました。フォーマット・lint・型チェックのように
速くて壊れやすいものを先に、時間のかかるテスト実行を後にする、という `static` /
`test` の分離思想（Stage 3 由来）を保っています。

### 手順D: `meta` ジョブを追加する

`jobs:` の先頭に `meta` ジョブを新設し、`pyproject.toml` からバージョン文字列を読み取って
`outputs.version` として公開するようにしました。既存の `test` ジョブは matrix 化されており
（Stage 3 参照）、matrix ジョブから `outputs` を持ち出すのは避ける設計判断（詳しくは
「つまずきポイント」を参照）のため、単独ジョブとして独立させています。

### 手順E: `gate` ジョブを書き換える

`needs` を `[meta, static, test]` に拡張し、ステップを3つに再構成しました。

1. `meta` / `static` / `test` の結果を Markdown の表として `$GITHUB_STEP_SUMMARY` に書く
2. PR のときだけ、カバレッジ artifact への案内を追記する
3. 依存ジョブの結果を判定し、`success` 以外が1つでもあれば `exit 1` する

3番目のステップの判定ロジックは Stage 3 から引き継いだ `read -ra results <<< "${DEPENDENCY_RESULTS}"`
の形をそのまま使っています。ブリーフでは単純な `for result in ${DEPENDENCY_RESULTS}` も
選択肢になり得ましたが、actionlint に同梱されている shellcheck がクォートなしの単語分割
（SC2086）を指摘するため、Stage 3 で確立した安全な形を維持しました。

### 手順F: push して確認する

```bash
git add pyproject.toml .github/workflows/ci.yml
git commit -m "ci: カバレッジゲート・mypy・ジョブ連携・ステップサマリを追加する"
git push origin stage/04-quality-gate
```

コミット `67cfa0a` を push した結果、PR #11 上で実行 ID `30281030295` がトリガーされ、
`gh run watch 30281030295 --exit-status` で全ジョブの完了を確認しました。結果は次のとおりです
（`gh pr checks 11` の出力）。

```
Lint & Test                              pass    4s
Metadata                                 pass    7s
Static Checks                            pass    12s
Test (ubuntu-latest / Python 3.12)       pass    12s
Test (ubuntu-latest / Python 3.13)       pass    13s
Test (windows-latest / Python 3.13)      pass    27s
```

新設した `Metadata` ジョブは単独で走って成功し、`Static Checks` には「型を確認する」が
ステップとして加わった状態で成功しました。`Lint & Test`（`gate`）は「結果をステップサマリに
書く」「PR 向けの案内を出す」「依存ジョブの結果を判定する」の3ステップ構成で成功しています。

以降の行番号は、**このステージ完了時点（タグ `stage-04`）の `ci.yml` を転記したブロック**の
行番号を指します。リポジトリの実ファイルを開いて数える必要はありません。

```
  1| # Stage 1 でアプリに CI を追加し、Stage 2 でトリガーを設計し直し、
  2| # Stage 3 でジョブを「静的検査」「テスト」「集約ゲート」の3層に分けた。
  3| # ruleset の必須チェック名 `Lint & Test` は集約ジョブ gate が引き継ぐ。
  4| name: CI
  5| 
  6| on:
  7|   # PR には必ず CI を走らせる。paths で絞らないのは、
  8|   # 必須チェックにしたときにドキュメントだけの PR が永久に待ち状態になるため。
  9|   pull_request:
 10|     branches: [main]
 11|   # main への push は、ドキュメントだけの変更なら省略してよい。
 12|   push:
 13|     branches: [main]
 14|     paths-ignore:
 15|       - "docs/**"
 16|       - "**/*.md"
 17| 
 18| # 同じブランチで新しい実行が始まったら、古い実行を止める。
 19| # main では途中で止めたくないので、PR のときだけキャンセルする。
 20| concurrency:
 21|   group: ${{ github.workflow }}-${{ github.ref }}
 22|   cancel-in-progress: ${{ github.event_name == 'pull_request' }}
 23| 
 24| # permissions: このワークフローが GITHUB_TOKEN に許す操作。
 25| # 最小権限にしておく。なぜ必要かは Stage 6 で回収する。
 26| permissions:
 27|   contents: read
 28| 
 29| env:
 30|   # actionlint はバージョンを固定して使う。docker タグの :latest は
 31|   # いつ中身が変わるか分からないため、教材としても避ける。
 32|   ACTIONLINT_VERSION: "1.7.12"
 33| 
 34| jobs:
 35|   # 後続ジョブに値を渡す例。outputs はジョブ間で文字列を受け渡す唯一の仕組みで、
 36|   # ランナーが別マシンである以上ファイルでは渡せない（Stage 0 で確認したとおり）。
 37|   meta:
 38|     name: Metadata
 39|     runs-on: ubuntu-latest
 40|     timeout-minutes: 5
 41|     outputs:
 42|       version: ${{ steps.read.outputs.version }}
 43|     steps:
 44|       - name: リポジトリを取得する
 45|         uses: actions/checkout@v7
 46| 
 47|       - name: pyproject.toml からバージョンを読む
 48|         id: read
 49|         run: |
 50|           version=$(grep -m1 '^version = ' pyproject.toml | cut -d '"' -f 2)
 51|           echo "読み取ったバージョン: ${version}"
 52|           # $GITHUB_OUTPUT に書いた key=value が、この step の outputs になる。
 53|           echo "version=${version}" >> "${GITHUB_OUTPUT}"
 54| 
 55|   static:
 56|     name: Static Checks
 57|     runs-on: ubuntu-latest
 58|     # ハングしたジョブが課金され続けるのを防ぐ。既定は 360 分と長い。
 59|     timeout-minutes: 10
 60|     steps:
 61|       - name: リポジトリを取得する
 62|         uses: actions/checkout@v7
 63| 
 64|       - name: uv と Python をセットアップする
 65|         uses: astral-sh/setup-uv@v7
 66|         with:
 67|           python-version: "3.12"
 68| 
 69|       - name: 依存関係をインストールする
 70|         run: uv sync --locked
 71| 
 72|       - name: フォーマットを確認する
 73|         run: uv run ruff format --check .
 74| 
 75|       - name: lint を確認する
 76|         run: uv run ruff check .
 77| 
 78|       - name: 型を確認する
 79|         run: uv run mypy src tools
 80| 
 81|       - name: 解説の行番号引用を検証する
 82|         run: uv run python tools/check_doc_citations.py docs/stages
 83| 
 84|       # ワークフロー自体も検査対象にする。式の綴り間違いや存在しない
 85|       # コンテキスト参照は、実行してみるまで気づけないことが多い。
 86|       - name: ワークフローを actionlint で検査する
 87|         run: |
 88|           docker run --rm \
 89|             --volume "${PWD}:/repo" \
 90|             --workdir /repo \
 91|             "rhysd/actionlint:${ACTIONLINT_VERSION}" -color
 92| 
 93|   test:
 94|     # matrix の値を名前に入れないと、3つの実行がすべて同じ名前になって
 95|     # どれが落ちたのか Checks 一覧から判別できない。
 96|     name: Test (${{ matrix.os }} / Python ${{ matrix.python-version }})
 97|     runs-on: ${{ matrix.os }}
 98|     timeout-minutes: 10
 99|     strategy:
100|       # 既定は true で、1つ落ちると残りが即座にキャンセルされる。
101|       # 「Windows だけ落ちるのか、両方落ちるのか」を知りたいので false にする。
102|       fail-fast: false
103|       matrix:
104|         os: [ubuntu-latest, windows-latest]
105|         python-version: ["3.12", "3.13"]
106|         # 全4通りは要らない。Windows は最新 Python だけ確認できれば十分、
107|         # という判断を exclude で表現する。組み合わせ爆発は matrix の主な失敗要因。
108|         exclude:
109|           - os: windows-latest
110|             python-version: "3.12"
111|     steps:
112|       - name: リポジトリを取得する
113|         uses: actions/checkout@v7
114| 
115|       - name: uv と Python をセットアップする
116|         uses: astral-sh/setup-uv@v7
117|         with:
118|           python-version: ${{ matrix.python-version }}
119| 
120|       - name: 依存関係をインストールする
121|         run: uv sync --locked
122| 
123|       - name: テストを実行する
124|         run: uv run pytest -v --cov-report=html
125| 
126|       # 失敗したときこそ中身を見たいので、成功時に限らず必ず上げる。
127|       - name: カバレッジ HTML を artifact として保存する
128|         if: always()
129|         uses: actions/upload-artifact@v7
130|         with:
131|           name: coverage-html-${{ matrix.os }}-${{ matrix.python-version }}
132|           path: htmlcov/
133|           retention-days: 7
134| 
135|   # 集約ゲート。ruleset が必須チェックとして見ているのはこのジョブの name。
136|   # 依存ジョブの構成を変えても、この名前さえ保てば ruleset を触らずに済む。
137|   gate:
138|     name: Lint & Test
139|     runs-on: ubuntu-latest
140|     needs: [meta, static, test]
141|     # 依存ジョブが失敗しても gate 自身は動かす必要がある。
142|     # if を書かないと、依存が1つでも失敗した時点で gate は skipped になり、
143|     # 必須チェックが「未報告」のまま PR が永久に待ち状態になる。
144|     if: always()
145|     timeout-minutes: 5
146|     steps:
147|       - name: 結果をステップサマリに書く
148|         env:
149|           APP_VERSION: ${{ needs.meta.outputs.version }}
150|           STATIC_RESULT: ${{ needs.static.result }}
151|           TEST_RESULT: ${{ needs.test.result }}
152|         run: |
153|           {
154|             echo "## CI 結果"
155|             echo ""
156|             echo "| 項目 | 値 |"
157|             echo "| --- | --- |"
158|             echo "| バージョン | ${APP_VERSION} |"
159|             echo "| 静的検査 | ${STATIC_RESULT} |"
160|             echo "| テスト | ${TEST_RESULT} |"
161|           } >> "${GITHUB_STEP_SUMMARY}"
162| 
163|       # PR のときだけ出す案内。if でステップ単位の出し分けができる。
164|       - name: PR 向けの案内を出す
165|         if: github.event_name == 'pull_request'
166|         run: |
167|           {
168|             echo ""
169|             echo "カバレッジの詳細は Artifacts の \`coverage-html-*\` を開いてください。"
170|           } >> "${GITHUB_STEP_SUMMARY}"
171| 
172|       - name: 依存ジョブの結果を判定する
173|         env:
174|           DEPENDENCY_RESULTS: ${{ join(needs.*.result, ' ') }}
175|         run: |
176|           echo "依存ジョブの結果: ${DEPENDENCY_RESULTS}"
177|           read -ra results <<< "${DEPENDENCY_RESULTS}"
178|           for result in "${results[@]}"; do
179|             if [ "${result}" != "success" ]; then
180|               echo "success ではない依存ジョブがあります"
181|               exit 1
182|             fi
183|           done
184|           echo "すべての依存ジョブが success です"
```

## 5. 何が変わったか

- **`--cov-fail-under=80` を `addopts`（31行目、`pyproject.toml` 側）に置いた理由**:
  `ci.yml` のコマンドライン引数（124行目 `uv run pytest -v --cov-report=html`）ではなく
  `pyproject.toml` の `addopts` に置くと、ローカルで `uv run pytest` を打つだけで CI と
  **同じ基準**が働きます。もし閾値を `ci.yml` 側のコマンドに書いていたら、ローカルでは
  素の `pytest` が通ってしまい、push して初めて CI で落ちる、という手戻りの多い運用に
  なっていたはずです。手順Bで確認したとおり、この閾値は実際に「効く」ものであり、
  表示するだけの数字ではなくなりました。
- **mypy を `static` ジョブ（79行目）に置いた理由**: `static` は `test` より速く終わる
  ジョブです（Stage 3 の実測では `Static Checks` が数秒〜十数秒、`test` は最長のレグで
  数十秒）。型の誤りのような「実行しなくても機械的に分かる」問題は、テストの完走を
  待たずに早く知りたいので、速くて壊れやすいチェックを集めた `static` に置いています。
- **`meta` ジョブと `outputs`（37〜53行目）**: `outputs` は、ジョブ間で値を渡す唯一の
  手段です。Stage 0 で確認したとおり、GitHub Actions の各ジョブは**別々のランナー
  （別マシン）**で実行されるため、ファイルに書いて次のジョブに引き継ぐようなことは
  できません。`meta` ジョブは `steps.read.outputs.version`（42行目）という**ステップの
  outputs** を `outputs.version`（同じく42行目）という**ジョブの outputs** に昇格させ、
  他のジョブから `needs.meta.outputs.version`（149行目）として参照できるようにしています。
- **`$GITHUB_OUTPUT` へ `key=value` を書く形式（53行目）**: `echo "version=${version}" >> "${GITHUB_OUTPUT}"`
  のように、`$GITHUB_OUTPUT` が指すファイルに `key=value` 形式の行を**追記**すると、
  そのステップの `steps.<id>.outputs.<key>` として後続から参照できるようになります。
  `${GITHUB_OUTPUT}` はシェルの環境変数展開であり、`${{ }}` 式ではありません。
- **`$GITHUB_STEP_SUMMARY` に Markdown を追記すると実行画面に表示されること（153〜161行目）**:
  `$GITHUB_STEP_SUMMARY` が指すファイルに書いた Markdown は、そのジョブの実行画面に
  レンダリングされた形で表示されます。実行 ID `30281030295` では、この仕組みで
  バージョン・静的検査結果・テスト結果の3行の表を書き込みました。
- **ステップ単位の `if:`（165行目、`github.event_name == 'pull_request'`）**: `if:` は
  ジョブだけでなくステップにも書けます。「PR 向けの案内を出す」ステップは PR イベントの
  ときだけ実行され、`main` への直接 push（`paths-ignore` を通過したドキュメント以外の
  push）では実行されません。同じジョブの中でも、イベント種別に応じて出す情報を
  出し分けられます。
- **`needs.<job>.result` と `join(needs.*.result, ' ')` の違い（150行目・174行目）**:
  `needs.static.result` のように具体的なジョブ名を指定すると、その1ジョブの結果
  （`success` / `failure` / `cancelled` / `skipped` のいずれか）を文字列として取得します。
  一方 `needs.*.result` は `needs` に列挙した**すべての**依存ジョブの結果を配列として
  まとめて取得する書き方で、`join(..., ' ')` と組み合わせるとスペース区切りの1つの
  文字列になります。前者は「特定の1ジョブの状態を表示したい」場面（148〜151行目）、
  後者は「依存ジョブ全部が success かどうかをまとめて判定したい」場面（172〜174行目）
  で使い分けています。

## 6. つまずきポイント

- **`--cov-fail-under` をワークフロー側のコマンド引数に書くと、ローカルと CI で基準が
  ズレる。** 必ず `pyproject.toml` の `addopts` に置いてください。ローカルで
  `uv run pytest` を打つだけの手軽な確認と、CI 上の確認が同じ基準を共有できます。
- **カバレッジ閾値は「上げ続ける」ものではありません。** 100% を目指すと、
  「行を実行させるためだけの、何も検証していないテスト」が増えていきます。閾値は
  「品質が落ちたことに気づく」ための道具であり、100% という数字そのものが目的では
  ありません。
- **`outputs` は文字列しか渡せません。** 真偽値のような値も、`"true"` / `"false"` という
  **文字列**として渡ってきます。後続のジョブで `if: needs.foo.outputs.flag` のように
  素朴に真偽判定に使うと、文字列 `"false"` は空文字列ではないため**真**と評価される、
  という落とし穴があります（比較するときは `== 'true'` のように明示的に文字列比較する
  必要があります）。
- **matrix ジョブの `outputs` は、最後に終わったジョブの値で上書きされ、どれが残るかは
  不定です。** `test` ジョブのように `strategy.matrix` で複数レグに展開されるジョブに
  `outputs` を持たせると、GitHub は各レグの `outputs` を同じジョブ名の下にまとめようと
  しますが、実際に採用されるのは「最後に完了したレグ」の値であり、実行順は保証されて
  いないため、どのレグの値が残るかは実行ごとに変わり得ます。本教材が `meta` を
  `test` とは別の単独ジョブにしたのはこのためです。バージョン文字列のように
  「1つに定まっているべき値」は、matrix ジョブから持ち出さず、専用の単独ジョブから
  出す設計にしています。
- **`$GITHUB_STEP_SUMMARY` は追記（`>>`）です。上書き（`>`）すると前のステップの内容が
  消えます。** `gate` ジョブの3つのステップのうち、最初の2つはどちらも
  `$GITHUB_STEP_SUMMARY` に書き込みます（161行目・170行目）。どちらも `>>` を使っているため、
  「結果をステップサマリに書く」で書いた表の下に、「PR 向けの案内を出す」の内容が
  積み重なります。もしどちらかで `>` を使っていたら、後から実行されたステップが
  前のステップの内容を消してしまいます。

## 7. 演習課題

以下の3問は [docs/stages/answers/stage-04.md](answers/stage-04.md) に解答があります。
まず自分で予想してから答えを見てください。

1. **問1**: テストを1つ削除してカバレッジを閾値未満まで下げ、CI が落ちることを確認する。
   落ちたときのログのどこに理由が出ているか答える。
2. **問2**: `gate` の要約に、失敗したジョブがあるときだけ警告行を足す。
3. **問3**: `meta` ジョブの `outputs` から `version` を消すと、`gate` のステップサマリは
   どう表示されるか予想し、確かめる。

## 8. 実務への持ち込みメモ

既存プロジェクトにカバレッジ閾値を入れるときは、**理想値**ではなく**現在の値**を
初期値にして、「これ以上下げない」運用から始めてください。「まずは80%を目指そう」の
ように理想値をいきなり閾値として設定すると、導入した瞬間から CI が赤くなり続け、
やがて「このプロジェクトの CI はどうせ赤い」という空気が定着して、誰も結果を
気にしなくなります。それはこのステージが解決しようとした「表示するだけの数字は
放置される」問題を、閾値という形を変えて再現しているだけです。現在の値を初期値にすれば、
閾値は「今の品質を守る」道具として機能し、そこから少しずつ引き上げていく運用が
成立します。
