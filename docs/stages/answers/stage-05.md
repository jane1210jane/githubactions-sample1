# Stage 5 演習課題 解答

[stage-05-reuse.md](../stage-05-reuse.md) の演習課題3問への解答です。
先に自分で予想してから読んでください。

## 問1: composite action の `run:` から `shell: bash` を消すとどうなるか確かめる

**予想**: ワークフローの `run:` はランナーの OS に応じた既定シェルを使いますが、
composite action はどの OS で呼ばれるか分からないため既定値を持ちません。
そのため `shell:` を省略すると `Required property is missing: shell` のような
エラーで落ちるだろう、と予想できます。

**実際に確かめる**: `stage/05-reuse` ブランチ上で、`.github/actions/setup-python-env/action.yml`
の「依存関係をインストールする」ステップから `shell: bash`
（[stage-05-reuse.md](../stage-05-reuse.md) の `action.yml` 転記ブロックにある最後の行）
の1行だけを削除して push しました（commit `fb8df90`、実行 ID `30286298647`）。

結果、予想はおおむね当たりましたが、**失敗する場所**は予想と違いました。
ワークフロー全体が構文解析の段階で弾かれたわけではなく、`Metadata`
ジョブ（composite action を使わない `meta`）は checkout からバージョン読み取りまで
最後まで正常に完了しました。composite action を実際に使う4つのジョブ
（`Checks / Static Checks`、`Checks / Test (ubuntu-latest / Python 3.12)`、
`Checks / Test (ubuntu-latest / Python 3.13)`、`Checks / Test (windows-latest /
Python 3.13)`）だけが、それぞれ「Python 環境をセットアップする」ステップに
到達した時点で失敗しました。実際に記録されたエラーメッセージは次のとおりです
（Linux ランナー・Windows ランナーのどちらでも同じ内容でした）。

```
Failed to load /home/runner/work/githubactions-sample1/githubactions-sample1/./.github/actions/setup-python-env/action.yml

GitHub.DistributedTask.ObjectTemplating.TemplateValidationException: The template is not valid.
/home/runner/work/githubactions-sample1/githubactions-sample1/./.github/actions/setup-python-env/action.yml
(Line: 26, Col: 7): Required property is missing: shell
```

（`Lint & Test` は `if: always()` により実行はされましたが、`static` と `test` の
すべてが `failure` だったため、依存ジョブ判定ステップが `exit 1` し、`Lint & Test`
自体も失敗として報告されました。）

**解答**: `shell:` を省略した composite action は、ワークフロー全体の構文エラーには
ならず、**その action を実際に `uses:` するステップに到達した時点で**「action の
manifest（`action.yml`）を読み込めない」という失敗になります。エラーメッセージ
`Required property is missing: shell` が示すとおり、composite action の
`runs.steps[].run` には `shell` が必須のプロパティであり、省略は許されません。
ワークフローの `run:` ステップは `runs-on` から決まる既定シェル（Linux/macOS は
`bash`、Windows は `pwsh`）を暗黙に使えますが、composite action はどの OS の
ランナーから呼ばれるか呼び出され側では分からないため、既定シェルという概念自体が
存在しません。

確認後、`git revert --no-edit HEAD` で `shell: bash` を復元し（commit `6afe964`）、
`git diff` で元のコミット（`1cc2051`）と `action.yml` に差分が無いことを確認し、
CI が全ジョブ green に戻ることも確認しています。

## 問2: `gate` ジョブを reusable workflow 側へ移すと何が起きるか予想し、実行はせずに説明する

**この実験は実行していません。** 実行すると `main` ブランチを保護している ruleset の
必須チェック名が報告されなくなり、以降すべての PR がマージ不能になる恐れがあるためです。
以下は Stage 5 で実際に確認した「呼び出すと `<呼び出し側ジョブ名> / <呼び出し先ジョブ名>`
に変わる」という実測結果（[stage-05-reuse.md](../stage-05-reuse.md) 第5節、
commit `271a130`・実行 ID `30285144196` で観測）から導いた説明です。

**予想と説明**: `gate`（`name: Lint & Test`）を `reusable-python-ci.yml` の
`jobs:` に移し、`ci.yml` 側からは `checks:` 経由で呼ぶだけの形にしたとします。
このとき `gate` は「`checks` という呼び出し側ジョブの中の、`gate` という呼び出し先
ジョブ」になるため、実際に PR の Checks 一覧に現れる名前は、`static` /
`test` が `Checks / Static Checks` / `Checks / Test (...)` になったのと同じ規則で、
**`Checks / Lint & Test`** に変わります。一方、このリポジトリの ruleset が必須
チェックとして要求している名前は文字どおり `Lint & Test` であり、`Checks / Lint &
Test` とは別の文字列です。GitHub は必須チェック名を**完全一致**で照合するため、
`Lint & Test` という名前のチェックは二度と報告されなくなり、すべての PR が
「Expected — Waiting for status to be reported」から進めなくなります
（[トラブルシューティング索引](../../troubleshooting.md) の該当項目と同じ症状です）。

これを避けるには、`gate`（集約ゲート）は常に**呼び出し元**に置き、reusable workflow
側には「呼び出される個々のチェック」だけを置く、という役割分担を守る必要があります。
本教材が `static` / `test` だけを `reusable-python-ci.yml` に切り出し、`gate` を
`ci.yml` に残しているのはこのためです。

## 問3: `python-versions` の既定値を `'["3.12"]'` に変え、呼び出し側で何も指定せずに実行する

**予想**: `test` の matrix は `os: [ubuntu-latest, windows-latest]` と
`python-version` の直積から、`exclude` で `windows-latest` × `3.12` を除いた
組み合わせになります。既定値を `'["3.12"]'` の1要素にすると、直積は
`ubuntu-latest × 3.12` と `windows-latest × 3.12` の2通りになり、そのうち
`windows-latest × 3.12` は `exclude` で除かれるため、残るのは `Test
(ubuntu-latest / Python 3.12)` の1つだけになるはずです。

**実際に確かめる**: `stage/05-reuse` ブランチ上で `reusable-python-ci.yml` の
`python-versions` の `default` を `'["3.12", "3.13"]'` から `'["3.12"]'` に変え、
`ci.yml` の `checks:` 側では `with:` を何も渡さずに push しました
（commit `0b4a5df`、実行 ID `30286377474`）。`gh pr checks 13` で観測した結果は
次のとおりです。

```
Checks / Static Checks                       pass
Checks / Test (ubuntu-latest / Python 3.12)  pass
Lint & Test                                  pass
Metadata                                     pass
```

**予想どおり、`Test` は `Checks / Test (ubuntu-latest / Python 3.12)` の1つだけに
なりました。** `windows-latest` の組み合わせは、`python-version` の候補が
`3.12` の1つしかない以上、必然的に `windows-latest × 3.12` になり、これは
`exclude` の対象そのものなので消えます。Checks の総数は通常の6件（`Static
Checks`・`Test` 3レグ・`Metadata`・`Lint & Test`）から4件に減りました。

**この演習からの教訓**: `exclude` は、matrix が実際に展開する組み合わせの**内容**
に対して「この組み合わせを除く」と書く仕組みです。Stage 5 より前は
`python-version: ["3.12", "3.13"]` がワークフローに直接書かれていたため、
`exclude` が何を除いているかは静的に読み取れました。ところが `workflow_call`
の `inputs` で `python-versions` を外から渡せるようにした結果、matrix の中身は
**呼び出し側が決める可変な値**になりました。今回のように呼び出し側の入力を変えると、
`exclude` に書いた `windows-latest` × `3.12` という組み合わせが、変わった後の
matrix の中に存在するかどうかも変わります。今回はたまたま「唯一残った組み合わせが
`exclude` に一致した」ため Windows の行が丸ごと消えましたが、`exclude` の記述自体は
一切変更していません。**入力で matrix を可変にすると、`exclude` が指す対象が
入力次第で変わり、意図せずレグが全部消える／逆に何も除かれなくなる、ということが
起こり得ます。** `exclude` を伴う matrix を `inputs` で外部化するときは、
入力側の変更が `exclude` の実際の効き方にどう波及するかを、レビュー時に
意識する必要があります。

確認後、`git revert --no-edit HEAD` で `default` を `'["3.12", "3.13"]'` に戻し
（commit `b50bbac`）、`git diff` で元のコミット（`1cc2051`）と
`reusable-python-ci.yml` に差分が無いことを確認し、CI が3レグ構成
（6件のチェックすべて green）に戻ることも確認しています。
