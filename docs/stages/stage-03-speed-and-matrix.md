# Stage 3: 高速化と再現性

## 1. このステージのゴール

- ジョブを分割して**並列に**走らせ、lint の指摘をテストの完了を待たずに知れるようにする。
- 複数の Python バージョン・複数の OS の組み合わせ（**matrix**）でテストし、
  「自分の環境（と CI の1環境）では動く」ではなく「宣言した環境すべてで動く」という
  保証に近づける。
- CI の実行時間そのものを意識できるようにする。ジョブを分けたことで生まれる並列化の効果、
  依存関係キャッシュが効いたときと効いていないときの差を、実測した数字で確認する。

## 2. 前提

- `stage-02` が完了していること。PR ごとに `Lint & Test` が走り、緑でなければマージできない状態。
- ローカルに `uv` と `gh` があること。本ステージでは Docker が使えれば
  actionlint をローカルでも確認できますが、必須ではありません（後述）。

## 3. なぜ必要か

`stage-02` までの CI には、体験してみると分かる2つの弱点が残っています。

1. **1通りの環境でしか試していない。** `ci.yml` の `test` ジョブは終始
   `ubuntu-latest` と Python `3.12` の組み合わせだけでテストを実行してきました。
   「CI が緑」は「その1通りの環境では動く」ことの保証にしかならず、
   利用者が Windows で動かしたときや、別の Python バージョンで動かしたときに
   壊れていないかは何もチェックしていません。「自分の環境では動く」という問題が、
   「CI の環境では動く」に置き換わっただけで、本質的には解決していません。
2. **lint とテストが直列に1つのジョブの中に並んでいる。** `フォーマットを確認する` →
   `lint を確認する` → `テストを実行する` は同じジョブの中の連続したステップなので、
   ステップとして表示は分かれていても、実行そのものは前から順番にしか進みません。
   テストの実行に時間がかかるプロジェクトほど、「フォーマット崩れがある」という
   数秒で分かるはずの指摘を知るまでに、テスト一式の完了を待たされることになります。

このステージでは、ジョブを**静的検査**・**テスト**・**集約ゲート**の3層に分けて
静的検査とテストを並列に走らせ、テストの中身をさらに OS × Python バージョンの
matrix に展開します。同時に、ワークフロー自体の書き間違いを検出する actionlint と、
Stage 2 で作った行番号引用検査ツールを CI に組み込みます。

## 4. 手順

### Step 1: 作業ブランチと PR を用意する

```bash
git switch -c stage/03-speed-and-matrix
git commit --allow-empty -m "chore: Stage 3 の作業を開始する"
git push -u origin stage/03-speed-and-matrix
gh pr create --title "Stage 3: 高速化と再現性" --body "..." --draft
```

PR を**先に draft で**開いておくと、以降のすべての push を `pull_request` イベントの
CI 実行として観察できます。draft のままにしておけば、途中の壊れた状態が
誤ってマージ対象として扱われる心配もありません。

### Step 2: 使用するアクション・イメージの実際のバージョンを確認する

Stage 1 で学んだとおり、「最新リリースのメジャー番号」と「実際に存在する浮動タグの
メジャー番号」は必ずしも一致しません。ここで新たに使う2つについても、リリース情報だけでなく
実物のタグを確認しました。

```bash
gh api repos/rhysd/actionlint/releases/latest --jq .tag_name
# → v1.7.12
gh api repos/actions/upload-artifact/git/matching-refs/tags/v --jq '.[].ref' | grep -E 'refs/tags/v[0-9]+$'
# → refs/tags/v1 〜 refs/tags/v7（最大は v7）
```

`actionlint` の Docker イメージタグには `v` を除いた `1.7.12` を、
`actions/upload-artifact` には浮動タグの最大値 `v7` を使います。

### Step 3: `ci.yml` を3層構成に書き換え、`test` を matrix 化する

`ci.yml` は2回に分けて書き換えました。まず `static` / `test` / `gate` の3ジョブへ分割し
（このときの `test` はまだ単一環境のまま）、actionlint と引用検査を `static` に組み込みました。
続けて `test` ジョブだけを matrix 化し、カバレッジ HTML を artifact として保存するステップを
追加しました。以下は **Stage 3 完了時点（タグ `stage-03`）の `ci.yml` をそのまま転記したもの**です。
本ドキュメント内の行番号の引用（このステップ以降すべて）は、**この転記ブロック内の行番号**を
指しており、リポジトリの実ファイルを開いて数える必要はありません。

<!-- transcript: .github/workflows/ci.yml @ stage-03 -->
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
 35|   static:
 36|     name: Static Checks
 37|     runs-on: ubuntu-latest
 38|     # ハングしたジョブが課金され続けるのを防ぐ。既定は 360 分と長い。
 39|     timeout-minutes: 10
 40|     steps:
 41|       - name: リポジトリを取得する
 42|         uses: actions/checkout@v7
 43|
 44|       - name: uv と Python をセットアップする
 45|         uses: astral-sh/setup-uv@v7
 46|         with:
 47|           python-version: "3.12"
 48|
 49|       - name: 依存関係をインストールする
 50|         run: uv sync --locked
 51|
 52|       - name: フォーマットを確認する
 53|         run: uv run ruff format --check .
 54|
 55|       - name: lint を確認する
 56|         run: uv run ruff check .
 57|
 58|       - name: 解説の行番号引用を検証する
 59|         run: uv run python tools/check_doc_citations.py docs/stages
 60|
 61|       # ワークフロー自体も検査対象にする。式の綴り間違いや存在しない
 62|       # コンテキスト参照は、実行してみるまで気づけないことが多い。
 63|       - name: ワークフローを actionlint で検査する
 64|         run: |
 65|           docker run --rm \
 66|             --volume "${PWD}:/repo" \
 67|             --workdir /repo \
 68|             "rhysd/actionlint:${ACTIONLINT_VERSION}" -color
 69|
 70|   test:
 71|     # matrix の値を名前に入れないと、3つの実行がすべて同じ名前になって
 72|     # どれが落ちたのか Checks 一覧から判別できない。
 73|     name: Test (${{ matrix.os }} / Python ${{ matrix.python-version }})
 74|     runs-on: ${{ matrix.os }}
 75|     timeout-minutes: 10
 76|     strategy:
 77|       # 既定は true で、1つ落ちると残りが即座にキャンセルされる。
 78|       # 「Windows だけ落ちるのか、両方落ちるのか」を知りたいので false にする。
 79|       fail-fast: false
 80|       matrix:
 81|         os: [ubuntu-latest, windows-latest]
 82|         python-version: ["3.12", "3.13"]
 83|         # 全4通りは要らない。Windows は最新 Python だけ確認できれば十分、
 84|         # という判断を exclude で表現する。組み合わせ爆発は matrix の主な失敗要因。
 85|         exclude:
 86|           - os: windows-latest
 87|             python-version: "3.12"
 88|     steps:
 89|       - name: リポジトリを取得する
 90|         uses: actions/checkout@v7
 91|
 92|       - name: uv と Python をセットアップする
 93|         uses: astral-sh/setup-uv@v7
 94|         with:
 95|           python-version: ${{ matrix.python-version }}
 96|
 97|       - name: 依存関係をインストールする
 98|         run: uv sync --locked
 99|
100|       - name: テストを実行する
101|         run: uv run pytest -v --cov-report=html
102|
103|       # 失敗したときこそ中身を見たいので、成功時に限らず必ず上げる。
104|       - name: カバレッジ HTML を artifact として保存する
105|         if: always()
106|         uses: actions/upload-artifact@v7
107|         with:
108|           name: coverage-html-${{ matrix.os }}-${{ matrix.python-version }}
109|           path: htmlcov/
110|           retention-days: 7
111|
112|   # 集約ゲート。ruleset が必須チェックとして見ているのはこのジョブの name。
113|   # 依存ジョブの構成を変えても、この名前さえ保てば ruleset を触らずに済む。
114|   gate:
115|     name: Lint & Test
116|     runs-on: ubuntu-latest
117|     needs: [static, test]
118|     # 依存ジョブが失敗しても gate 自身は動かす必要がある。
119|     # if を書かないと、依存が1つでも失敗した時点で gate は skipped になり、
120|     # 必須チェックが「未報告」のまま PR が永久に待ち状態になる。
121|     if: always()
122|     timeout-minutes: 5
123|     steps:
124|       - name: 依存ジョブの結果を判定する
125|         env:
126|           DEPENDENCY_RESULTS: ${{ join(needs.*.result, ' ') }}
127|         run: |
128|           echo "依存ジョブの結果: ${DEPENDENCY_RESULTS}"
129|           read -ra results <<< "${DEPENDENCY_RESULTS}"
130|           for result in "${results[@]}"; do
131|             if [ "${result}" != "success" ]; then
132|               echo "success ではない依存ジョブがあります"
133|               exit 1
134|             fi
135|           done
136|           echo "すべての依存ジョブが success です"
```

`ci.yml` の `gate` ジョブ（124〜136行目）の依存結果判定は `read -ra results <<< "${DEPENDENCY_RESULTS}"`
（129行目）でスペース区切りの文字列を配列に読み込んでからループしています（130行目）。
これは、actionlint の Docker イメージに同梱されている shellcheck が、
`for result in ${DEPENDENCY_RESULTS}; do`（クォートなしの単語分割）を
指摘するのを避けるための書き方です。挙動そのもの（`success` 以外の結果が1つでもあれば
`exit 1` する）は変わりません。

### Step 4: push して `Static Checks` / `Test` / `Lint & Test` の3つが緑になることを確認する

```bash
git add .github/workflows/ci.yml
git commit -m "ci: ジョブを静的検査・テスト・集約ゲートの3層に分け actionlint を導入する"
git push
gh pr checks 9 --watch
```

実行 ID `30276072947` で確認した `gh pr checks 9` の結果です（この時点では `test` はまだ
matrix 化前で、`Test` という1つのチェックでした）。

```
Lint & Test     pass   3s
Static Checks   pass   15s
Test            pass   7s
```

`ci.yml` の actionlint のステップ（`ワークフローを actionlint で検査する`、63〜68行目）は
`ci.yml` と Stage 0 由来の `hello.yml` の両方を検査しますが、どちらにも指摘はありませんでした。
なお、この環境には Docker が入っておらず（`docker: command not found`）、
ローカルでの事前確認は行わず、CI 上の `Static Checks` ジョブでの実行結果だけを見ています。

### Step 5: `if: always()` の必要性を実測する

`ci.yml` の `gate` の `if: always()`（121行目）を一時的にコメントアウトし、`static` の
`lint を確認する` ステップをわざと失敗させて push しました。

実行 ID `30276142870` での `gh pr checks 9` の結果です。

```
Static Checks   fail       5s
Lint & Test     skipping   0
Test            pass       8s
```

`ci.yml` の `static` が失敗すると、`needs: [static, test]`（117行目）を持つ `gate` は
`if: always()` が無い状態では実行条件を満たさず、**failed ではなく skipped** になります。
実行結果一覧の `gate` の行も `- Lint & Test in 0s` と表示され、失敗としてではなく
未実行として扱われていました。skipped は success でも failure でもないため、
ruleset から見ると必須チェック `Lint & Test` は「まだ結果が来ていない」状態のままになり、
PR は赤く表示されることすらなく、ただマージできないまま止まります。

### Step 6: 実験を戻す

```bash
git revert --no-edit HEAD
git push
gh pr checks 9 --watch
```

実行 ID `30276199312` で3つとも緑に戻ったことを確認しました。`if: always()` はこの時点で
`ci.yml` の121行目に復元されています。

### Step 7: `.gitignore` とローカルでのカバレッジ HTML 生成を確認する

`.gitignore` にはもともと `htmlcov/` が含まれていたため変更不要でした。
ローカルでは次のコマンドで `htmlcov/index.html` が生成されることを確認しました。

```bash
uv run pytest -q --cov-report=html && ls htmlcov/index.html
```

### Step 8: push して matrix の3レグが揃うことを確認する

`ci.yml` の `test` ジョブを70〜110行目の内容（matrix・artifact 保存を含む）に置き換えて push しました。

```bash
git add .github/workflows/ci.yml
git commit -m "ci: テストを matrix 化しカバレッジ HTML を artifact に保存する"
git push
gh pr checks 9 --watch
```

実行 ID `30276817955` での `gh pr checks 9` の結果です。

| Check | 結果 | 所要時間 |
|---|---|---|
| Lint & Test | pass | 5s |
| Static Checks | pass | 9s |
| Test (ubuntu-latest / Python 3.12) | pass | 12s |
| Test (ubuntu-latest / Python 3.13) | pass | 14s |
| Test (windows-latest / Python 3.13) | pass | 41s |

`ci.yml` の `os: [ubuntu-latest, windows-latest]` × `python-version: ["3.12", "3.13"]`（81〜82行目）の
組み合わせは本来4通りですが、`exclude`（85〜87行目）で `windows-latest` × `3.12` を除いたため、
実際に走ったのは3レグです。`windows-latest` のレグは初回から成功し、
このプロジェクトのテストスイートを Windows 上で動かすための追加対応は不要でした。

### Step 9: uv のキャッシュが効いていることを観察する

初回の push（実行 ID `30276817955`）の時点では、`ubuntu-latest / 3.12` のキャッシュキーは
既存（Stage 1・2 で使ってきたキー）と一致して `Cache hit` しましたが、`ubuntu-latest / 3.13` と
`windows-latest / 3.13` は matrix で初めて生成したキーだったため、どちらも `Cache miss` でした。
つまり1回の push だけでは「2回目以降で速くなる」ことを3レグとも比較できません。
そこで `gh run rerun 30276817955` で**同じ実行を再実行**しました（新しいコミットは作らず、
同じ run id が再利用されます）。`依存関係をインストールする`（`uv sync --locked`）ステップの
所要時間を1回目とrerun後の2回目で比べた結果です。

| レグ | 1回目 | 2回目（`gh run rerun` 後） |
|---|---|---|
| ubuntu-latest / 3.12（1回目から hit） | <1s（hit） | <1s（hit） |
| ubuntu-latest / 3.13（1回目は miss） | 約2s（**miss**） | 約2s（hit） |
| windows-latest / 3.13（1回目は miss） | **約20s（miss）** | **約8s（hit）** |

もっとも変化が大きかったのは `windows-latest / 3.13` で、`uv sync` 部分が約20秒から約8秒に、
ジョブ全体では41秒から29秒に縮みました。**キャッシュの効果を確かめる方法は「もう一度 push する」
ではなく「同じ実行を再実行する（`gh run rerun`）」でした。** 新しい push では毎回新しいコミット
SHA に対して新しい実行が作られますが、依存関係のキャッシュキー自体は `uv.lock` の内容など
コミット SHA とは別の要素で決まるため、push し直さなくても再実行だけでキャッシュの効きを
再現できます。

### Step 10: artifact がダウンロードできることを確認する

```bash
gh run download 30276817955 --name coverage-html-ubuntu-latest-3.12 --dir /tmp/cov-check
ls /tmp/cov-check/index.html
```

`index.html` を含む `htmlcov/` 相当の一式が取得できることを確認しました。

## 5. 何が変わったか

以下の行番号は、Step 3 で転記した `ci.yml`（タグ `stage-03` 時点の内容）の行番号です。

- **`ci.yml` でジョブを3つに分けた理由と `needs:` による依存関係**（`jobs:` 34行目、`static:` 35行目、
  `test:` 70行目、`gate:` 114行目、`needs: [static, test]` 117行目）: `static`（lint・format・
  引用検査・actionlint）と `test`（pytest）は互いの結果に依存しないため、別ジョブにすれば
  GitHub 側が自動的に**並列**に実行します。`gate` だけは `needs: [static, test]`（117行目）で
  両方の完了を待ち、両方の結果を集約してから成否を決めます。
- **`gate` ジョブが `Lint & Test` という名前を引き継いでいる理由**（112〜113行目のコメント、
  115行目 `name: Lint & Test`）: Stage 2 の演習3で予告したとおり、ruleset の必須チェックは
  ジョブの `name:` という文字列に紐づいています。ジョブの中身を3層に再構成しても、
  集約ジョブ `gate` の `name:` さえ元のジョブと同じ `Lint & Test` に保っておけば、
  ruleset 側の設定（必須チェック名）を一切変更せずに済みます。
- **`if: always()` が無いと `gate` が skipped になり、必須チェックが未報告になること**
  （121行目）: 上記の手順 Step 5 で実測したとおり（実行 ID `30276142870`）、`static` を
  わざと失敗させた状態で `if: always()` を外すと、`gate` は `failed` ではなく `skipped` に
  なりました。GitHub の既定の挙動では、`needs:` に指定したジョブが1つでも成功しなかった場合、
  後続ジョブは実行条件を満たさず自動的に skipped 扱いになります。`if: always()`（121行目）を
  付けることで、依存ジョブの成否にかかわらず `gate` 自身は必ず実行され、
  依存の結果を自分の判断（124〜135行目）で success/failure に変換して報告できるようになります。
- **`strategy.matrix` と `exclude` による組み合わせの絞り込み**（80〜87行目）: `matrix:`
  （80行目）に列挙した軸（`os`、`python-version`）は、指定しない限り**すべての直積**
  （このケースでは2×2の4通り）に展開されます。`exclude:`（85〜87行目）はその直積から
  特定の組み合わせを取り除く指定で、ここでは「Windows は最新の Python バージョンだけ確認できれば
  十分」という判断のもと `windows-latest` × `"3.12"` を除外し、実行を4通りから3通りに
  減らしています。
- **`fail-fast: false` を選んだ理由**（77〜79行目）: `strategy.fail-fast` の既定値は `true` で、
  matrix のどれか1つが失敗すると、GitHub は残りの matrix ジョブを即座にキャンセルします。
  「残り」には、その時点で**実行中**のジョブだけでなく、ランナーの空きを待って**まだ
  開始していない待機中（queued）**のジョブも含まれます。今回は「Windows だけの問題なのか、
  Python バージョン全体の問題なのか」を切り分けたいため、`false`（79行目）にして
  すべてのレグを最後まで走らせています。
- **`timeout-minutes` の意味と既定値**（38〜39行目、75行目、122行目）: GitHub Actions の
  ジョブには `timeout-minutes` を指定しない場合の既定値があり、38行目のコメントのとおり
  **既定は360分**です。ハングしたジョブ（無限ループやプロンプト待ちなど）があると、
  この既定値いっぱいまでランナーを占有し続け、実行時間・料金の両方を無駄にします。
  `static`（39行目、10分）・`test`（75行目、10分）・`gate`（122行目、5分）それぞれに
  実際にかかる時間より少し余裕を持たせた上限をつけています。
- **`actions/upload-artifact` と `if: always()` の組み合わせ**（103〜110行目）:
  カバレッジ HTML を保存するステップは `if: always()`（105行目）を付けており、
  直前の `テストを実行する` ステップが失敗しても実行されます。テストが失敗したときこそ
  「どこがどう落ちたか」をカバレッジレポートで確認したい場面なので、成功時限定にしてしまうと
  一番見たいときに artifact が無い、ということになります。
- **`env:` でバージョンを固定した actionlint を Docker で実行していること**（29〜32行目、
  61〜68行目）: `env.ACTIONLINT_VERSION`（32行目）で `1.7.12` を固定し、Docker イメージタグ
  `"rhysd/actionlint:${ACTIONLINT_VERSION}"`（68行目）に埋め込んで実行しています。
  イメージタグに `:latest` を使わないのは、`latest` がいつどう変わるか分からず、
  今日通った CI が明日いきなり別バージョンの actionlint の指摘で落ちる、という
  再現性の無い失敗を避けるためです（`env:` という書き方自体の詳しい理由は Stage 6 で扱います）。

## 6. つまずきポイント

- **matrix の値をジョブ名に入れないと、Checks 一覧で全部同じ名前になり、どれが落ちたか分からない。**
  `ci.yml` の `test:` の `name:`（73行目）は `Test (${{ matrix.os }} / Python ${{ matrix.python-version }})`
  のように matrix の値を埋め込んでいます。これが無いと3つのレグがすべて `Test` という
  同じ名前で並び、GitHub の Checks 一覧からはどの組み合わせが失敗したのか判別できません。
- **matrix を入れるとジョブ名が変わるため、必須チェック名を保つ設計をしないと全 PR が
  マージ不能になる。** `test` を matrix 化した結果、報告されるチェック名は `Test` から
  `Test (ubuntu-latest / Python 3.12)` のような3つの名前に変わりました。もし ruleset の
  必須チェックが元の `Test` という名前を指していたら、matrix 化した瞬間にその名前は
  二度と報告されなくなり、既存の全 PR がマージ不能になっていたはずです。本教材でこれが
  問題にならなかったのは、必須チェックが `test` 自体ではなく `gate` の `name: Lint & Test`
  （115行目、matrix の影響を受けない固定名）を指しているためです。
- **`if: always()` を忘れると、依存ジョブの失敗が「チェック未報告」として現れ、失敗より
  紛らわしい。** Step 5 で実測したとおり、`gate` が skipped になっても PR 画面は
  「失敗」ではなく「まだ結果待ち」に見えます。慣れないうちは、赤い×を探して
  見つからないまま「なぜマージできないのか」で長く悩むことになります。
- **`exclude` の値は文字列として厳密一致する。`"3.12"` と `3.12` は別物。** 85〜87行目の
  `exclude` は `python-version: "3.12"` のようにクォート付きで書く必要があります。
  `matrix.python-version`（82行目）自体も `["3.12", "3.13"]` と文字列として定義しており、
  クォートを外すと YAML はそれを浮動小数点数 `3.12` として解釈します。`exclude` の側の
  値が数値になり `matrix` の側の値が文字列のままだと、両者は一致せず、除外したはずの
  組み合わせが除外されないまま4通り実行される、という気付きにくいズレが起こります。
- **Windows ランナーの既定シェルは PowerShell Core（`pwsh`）。`run:` に Bash 前提の
  コマンドを書くと落ちる。** Windows のプリインストールである Windows PowerShell
  （`powershell.exe`）ではなく、クロスプラットフォームの PowerShell Core が既定になっている
  点に注意してください。`runs-on: ${{ matrix.os }}`（74行目）で `windows-latest` になったレグでも、`run:`
  ステップ（97〜98行目、100〜101行目）はどちらも `uv sync --locked` /
  `uv run pytest -v --cov-report=html` という、OS を問わず動くコマンドだけにしてあります。
  Windows 固有の対処が必要な場面は README の
  [Windows で進める場合](../../README.md#windows-で進める場合) を参照してください。
- **artifact 名が重複すると上書き・失敗の原因になるため matrix の値を名前に含める。**
  108行目の `name: coverage-html-${{ matrix.os }}-${{ matrix.python-version }}` は
  matrix の値を含めているため、3レグそれぞれ `coverage-html-ubuntu-latest-3.12` のように
  異なる名前になります。`actions/upload-artifact@v4` 以降（本教材は v7 系を使用。
  Stage 6 以降はタグではなく SHA でピン留めしています）では、
  同じ実行内で同名の artifact を複数回アップロードするとエラーで失敗します。
  上書きしたい場合は `overwrite: true` を明示する必要があります。
- **`if: always()`（121行目）は、依存ジョブが `failure` になった場合だけでなく、
  `cancelled` になった場合にも `gate` を実行します。** `concurrency.cancel-in-progress`
  （22行目）は PR イベントで有効なため、同じブランチに連続して push すると、古い方の
  実行の依存ジョブは `cancelled` になります。`if: always()` はこの `cancelled` な
  依存ジョブに対しても `gate` を動かし、「依存ジョブの結果を判定する」ステップ
  （124〜135行目）が `cancelled` を `success` 以外として検出して `exit 1` するため、
  古い方の実行では必須チェック `Lint & Test` が**失敗**として報告されます。
  実行 ID `30286356455` で、呼び出し先のジョブがすべて `cancelled` になり、
  `Metadata` は `success`、`Lint & Test` は `failure` として報告される様子を
  実際に観測しました。取り残された古い実行の `Lint & Test` が赤いままなのは
  想定内の挙動であり、対象の PR では最新の実行が緑であれば問題ありません。
  「失敗したときだけ動かしたい」なら、キャンセルを除外する `!cancelled()` の方が
  `always()` より狭い条件として使えます。

## 7. 演習課題

以下の3問は `docs/stages/answers/stage-03.md` に解答があります。
まず自分で予想してから答えを見てください。

1. **問1**: `fail-fast` を既定（`true`）に戻し、`windows-latest` のテストだけをわざと失敗させて、
   `fail-fast: false` のときと挙動を比べる。
2. **問2**: `gate` ジョブの `name:` を `CI Gate` に変えると何が起きるか予想し、**実行はせずに**
   説明する。
3. **問3**: matrix に `python-version: "3.11"` を追加すると何が起きるか。実際に追加して確かめる。

## 8. 実務への持ち込みメモ

matrix は「サポートすると宣言した環境」と一致させてください。動かせるからといって
組み合わせをむやみに増やすと、実行時間・料金・そして「このレグはなぜあるのか」を
説明するコストだけが増えていきます。逆に、宣言した環境の一部を matrix から外していると、
「CI は緑なのに、宣言した環境の1つでは実際には動かない」という状態に気づけません。

CI の所要時間は開発速度そのものです。プルリクエストを出してからレビューできる状態になるまでの
時間が長いほど、コンテキストスイッチのコストが増え、開発のリズムが崩れます。
`timeout-minutes` と依存関係のキャッシュ（`astral-sh/setup-uv` が自動で行っています）は、
プロジェクトの初期段階から入れておいてください。後から入れようとすると、
「今まで既定の360分でも誰も困っていなかった」という慣性が働き、優先順位が上がりにくくなります。

そして、組み合わせを1つ増やす前に、「その組み合わせは本当に守るべき約束か」を問うてください。
守る約束が増えるということは、matrix のレグが増え、CI 時間が伸び、`exclude` の管理も
複雑になるということです。約束していないものまで matrix に含めるのは、
将来外すときの心理的なハードルを上げるだけで、今すぐ得られる価値はほとんどありません。
