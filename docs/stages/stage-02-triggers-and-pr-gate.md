# Stage 2: トリガー設計と PR ゲート

## 1. このステージのゴール

- **PR ごとに CI が走り、緑でなければマージできない**状態にする。
- Stage 1 までの CI は「壊れたら赤くなる」ところまでしか作っていませんでした。
  赤いままでも `git push` は通ってしまい、`main` に壊れたコードが入り続けられる状態でした。
  このステージでは、CI の結果を**実際にマージを止める力**に変えます。
- これ以降、このリポジトリ自体の開発は PR ベースに切り替わります
  （`main` への直接 push ができなくなります）。

## 2. 前提

- `stage-01` が完了していること。`.github/workflows/ci.yml` が `push` のたびに動き、
  `ruff format --check` / `ruff check` / `pytest` を実行して結果を報告する状態。
- `gh` コマンド（GitHub CLI）が使えること。ruleset の確認に使います。

## 3. なぜ必要か

Stage 1 の CI には、体験してみると分かる大きな穴が残っています。

1. **CI が赤くても push できてしまう**。`ci.yml` は「結果を報告するだけ」で、
   その結果を見るかどうかは人間の注意力に委ねられていました。忙しいときや、
   通知を見逃したときは、壊れたコードがそのまま `main` に残り続けます。
   無視できるチェックは、存在しないのと同じです。
2. **`main` に push するたびに、無関係なワークフローまで一緒に起動してしまう**。
   Stage 0〜1 はまだ `main` に直接 push する運用だったため、これは実際に体験した痛みです。
   Stage 1 の `ci.yml` の `on: push:` はブランチもパスも絞っていないため、
   ドキュメントを1行直しただけの push でも `Lint & Test` が走ります。しかも `hello.yml`
   （Stage 0 の学習用ワークフロー、当時は `on:` に `push:` も残っていました）まで
   一緒に起動していました。`main` へ push するたびに本来不要なワークフローの実行が
   積み重なっていたのが実情です。

このステージでは、この2つを「トリガー設計」と「ruleset によるゲート化」で解決します。

## 4. 手順

### Step 1: 作業ブランチを作る

```bash
git switch -c stage/02-triggers
```

このステージからは `main` へ直接 push できなくなるため、最初から作業用ブランチで進めます。

### Step 2: `ci.yml` のトリガーと `concurrency` を書き換える

`on:` を `pull_request:`（`main` 向け）と `push:`（`main` 向け、`docs/` と `*.md` は除外）に、
`concurrency:` を追加しました。以下は **Stage 2 完了時点（本リポジトリの現在のタグ `stage-02`）の
内容をそのまま転記したもの**です。本ドキュメント内の行番号の引用（このステップと次の
「5. 何が変わったか」節）は、すべて**この転記ブロック内の行番号**を指しており、
リポジトリの実ファイルを開いて数える必要はありません。

```
  1| # Stage 1 でアプリに CI を追加し、Stage 2 でトリガーを設計し直した。
  2| # 現在は PR には必ず、main への push はドキュメントのみの変更を除いて
  3| # lint とテストを走らせ、PR は Lint & Test が緑でなければマージできない
  4| # （ruleset によるゲートは .github/workflows/ の外、リポジトリ設定側にある）。
  5| name: CI
  6|
  7| on:
  8|   # PR には必ず CI を走らせる。paths で絞らないのは、
  9|   # 必須チェックにしたときにドキュメントだけの PR が永久に待ち状態になるため。
 10|   pull_request:
 11|     branches: [main]
 12|   # main への push は、ドキュメントだけの変更なら省略してよい。
 13|   push:
 14|     branches: [main]
 15|     paths-ignore:
 16|       - "docs/**"
 17|       - "**/*.md"
 18|
 19| # 同じブランチで新しい実行が始まったら、古い実行を止める。
 20| # main では途中で止めたくないので、PR のときだけキャンセルする。
 21| concurrency:
 22|   group: ${{ github.workflow }}-${{ github.ref }}
 23|   cancel-in-progress: ${{ github.event_name == 'pull_request' }}
 24|
 25| # permissions: このワークフローが GITHUB_TOKEN に許す操作。
 26| # 最小権限にしておく。なぜ必要かは Stage 6 で回収する。
 27| permissions:
 28|   contents: read
 29|
 30| jobs:
 31|   test:
 32|     name: Lint & Test
 33|     runs-on: ubuntu-latest
 34|     steps:
 35|       # Stage 0 で見たとおり、ランナーは空。まずリポジトリを持ってくる。
 36|       - name: リポジトリを取得する
 37|         uses: actions/checkout@v7
 38|
 39|       - name: uv と Python をセットアップする
 40|         uses: astral-sh/setup-uv@v7
 41|         with:
 42|           python-version: "3.12"
 43|
 44|       # --locked: uv.lock と pyproject.toml がずれていたら失敗させる。
 45|       # ローカルと CI で違う依存が入る事故を防ぐ。
 46|       - name: 依存関係をインストールする
 47|         run: uv sync --locked
 48|
 49|       - name: フォーマットを確認する
 50|         run: uv run ruff format --check .
 51|
 52|       - name: lint を確認する
 53|         run: uv run ruff check .
 54|
 55|       - name: テストを実行する
 56|         run: uv run pytest -v
```

ファイル冒頭のコメント（1〜4行目）は Stage 1 で CI を追加し Stage 2 でトリガーを設計し直した
という経緯と、現在のトリガー条件を説明しています。`permissions:`（27〜28行目）には、
`hello.yml` と同様に「なぜ必要かは Stage 6 で回収する」というコメントを付けています。

### Step 3: `hello.yml` の `push` トリガーを外す

`.github/workflows/hello.yml` の `on:` から `push:` を削除し、`workflow_dispatch:` のみを残しました。
Stage 0 の学習用ワークフローが毎回の push で起動するのは邪魔なだけなので、手動起動専用にします。

### Step 4: YAML を検証してコミットし、PR を作る

```bash
python -c "import yaml; [yaml.safe_load(open(p, encoding='utf-8')) for p in ('.github/workflows/ci.yml','.github/workflows/hello.yml')]" && echo OK
git add .github/workflows/
git commit -m "ci: トリガーを設計し直し concurrency を追加"
git push -u origin stage/02-triggers
gh pr create --title "Stage 2: トリガー設計と PR ゲート" --body "CI のトリガーを PR 中心に変更し、concurrency で無駄な実行を止める。"
```

### Step 5: PR で CI が走ることを確認する

`gh pr checks 1 --watch` で確認したところ、`Lint & Test` が成功しました
（実行 ID `30222505153`）。実行ログの `event` を確認すると `pull_request` になっており、
Stage 1 までの `push` とは別のイベントで起動していることが分かります。

### Step 6: `concurrency` が効くことを確認する

同じブランチに続けて push すると、先に始まった実行がキャンセルされることを確認しました。
実際には、間隔が短すぎると GitHub 側で push イベントの配信そのものがまとめられてしまい
（webhook が来ないので新しい実行自体が作られない）、間隔が空きすぎると
先の実行が `cancel-in-progress` の判定より先に終わってしまいます。
このステージでは何回か push の間隔を調整し、次の3件の実行で確認できました。

| 実行 ID | コミット | 結果 |
|---|---|---|
| `30222630334` | `62f2a8e` | `cancelled`（後続の push により打ち消された） |
| `30222631716` | `10b6f99` | `cancelled`（同上） |
| `30222633234` | `ae1c622` | `success`（最後の push だけが最後まで走った） |

`cancelled` になった実行は赤（失敗）ではなく灰色で表示されます。これは異常ではなく、
`concurrency` が設計どおりに動いた結果です。

### Step 7: ruleset で必須チェックを設定する

本来は GitHub の Web UI で設定する操作です（リポジトリ → Settings → Rules → Rulesets →
New ruleset → New branch ruleset）。手順は次のとおりです。

1. Ruleset Name に `main protection` を入力し、Enforcement status を **Active** にする。
2. Target branches → Add target → **Include default branch** を選ぶ。
3. Rules で以下を有効にする。
   - **Require a pull request before merging**（Required approvals は `0` にする。1 人で学習しているため）
   - **Require status checks to pass** → Add checks → `Lint & Test` を選択
4. Create をクリックして保存する。

> **実施メモ**: 今回はブラウザを使えない環境で作業したため、上記と同じ設定を
> GitHub API（`POST /repos/{owner}/{repo}/rulesets`）経由で作成しました。
> UI から作る場合とリポジトリに反映される内容は同一です。実際に学習する際は、
> 上記の UI 手順で一度自分の手で設定することをお勧めします。API で作成した場合は
> `gh api repos/<owner>/<repo>/rulesets` で内容を確認できます（今回の ruleset id は
> `19779055`）。

### Step 8: ゲートが効いていることを確認する

```bash
git switch main
git commit --allow-empty -m "test: main への直接 push が拒否されることを確認する"
git push
```

実際に次のエラーで push が拒否されることを確認しました。

```
remote: - Changes must be made through a pull request.
remote: - Required status check "Lint & Test" is expected.
 ! [remote rejected] main -> main (push declined due to repository rule violations)
```

確認用のコミットは `git reset --hard HEAD~1` で取り消しました。

### Step 9: PR をマージする

```bash
git switch stage/02-triggers
gh pr merge --squash --delete-branch
git switch main
git pull
```

`Lint & Test` が緑だったため、`--admin` などのバイパスなしで通常どおりマージできました。

## 5. 何が変わったか

以下の行番号は、Step 2 で転記した `ci.yml`（タグ `stage-02` 時点の内容）の行番号です。

- **`pull_request` と `push` の違い**（`ci.yml` 10〜11行目 と 13〜17行目）:
  `push` はブランチの現在の状態に対して走りますが、`pull_request` は**マージ後の状態
  （ベースブランチと自分のブランチをマージしたコミット）**に対して走ります。
  そのため、「自分のブランチ単体では通ったのに、`main` の最新と合わせた PR では落ちる」
  ということが起こり得ます。これはコンフリクトはしていなくても、両方の変更を
  同時に適用した結果おかしくなるケースがある、という意味です。
- **`branches:` / `paths-ignore:` によるフィルタ**（`ci.yml` 11行目・14行目・15〜17行目）:
  `pull_request:` 側は `branches: [main]`（11行目）だけを条件にし、`paths` では絞りません。
  `push:` 側は `branches: [main]`（14行目）に加えて `paths-ignore:`（15〜17行目）で
  `docs/**` と `**/*.md` を除外しています。ドキュメントだけの
  変更で `main` に push するときまで lint とテストを走らせる必要はないためです。
  なぜ `pull_request` 側に `paths-ignore` を付けないのかは、次の「つまずきポイント」で
  説明します。
- **`concurrency` の `group` と `cancel-in-progress`**（`ci.yml` 19〜23行目）:
  `group` が同じ実行同士だけが打ち消し合います。今回の `group: ${{ github.workflow }}-${{ github.ref }}`
  （22行目）は「ワークフロー名 + ブランチ（または PR の ref）」の組み合わせなので、
  同じブランチ・同じ PR 内で新しい実行が始まったときだけ古い実行が対象になります。
  他のブランチや他の PR の実行には影響しません。
- **`cancel-in-progress` を PR のときだけ有効にした理由**（`ci.yml` 23行目）:
  `${{ github.event_name == 'pull_request' }}` という式にすることで、PR 上の実行
  （何度も push し直す途中経過）はどんどんキャンセルして最新だけを見ればよい一方、
  `main` に対する実行は最後まで走らせています。`main` の実行結果は README のバッジや
  リリース判断に使われるため、途中で握りつぶしたくないという判断です。
- **ruleset はリポジトリ側の設定であり、YAML には現れない**: 今回追加した
  「PR 必須」「`Lint & Test` が緑であること」というルールは、`.github/workflows/` の
  どのファイルにも書かれていません。ワークフローの YAML だけを読んでも、
  「マージが CI 結果でブロックされている」ことは分かりません。設定は
  GitHub の Settings → Rules 側（または API の `rulesets` エンドポイント）にあります。

## 6. つまずきポイント

- **`pull_request` に `paths` フィルタを付けて必須チェックにすると、PR が永久に待ち状態になる。**
  これが、本ステージで `paths-ignore` を `push:` 側にだけ付け、`pull_request:` 側には
  付けなかった理由です。フィルタでワークフロー自体がスキップされると、GitHub はその
  チェックを「失敗」ではなく「未報告（Expected — Waiting for status to be reported）」
  として扱います。必須チェックが未報告のままだと、PR は**いつまで経ってもマージ可能に
  なりません**。
- **必須チェックはジョブの `name:` で指定する。`jobs:` のキー名ではない。**
  `ci.yml` では `jobs:` のキーは `test`（31行目）ですが、ruleset に登録したチェック名は
  `Lint & Test`（32行目の `name:`）です。もし `name:` を変更すると、GitHub 側から見て
  「`Lint & Test` という名前のチェックがもう報告されなくなった」ことになり、
  ruleset の必須チェック設定はエラーにもならず**無言で無効化**されます
  （正確には、そのチェックがずっと「未報告」のままになり、PR がマージできなくなります）。
- **`concurrency` で古い実行がキャンセルされるのは正常。** 赤（失敗）ではなく
  灰色の `cancelled` として表示されます。「テストが落ちた」わけではないので、
  ログを調べる必要はありません。ただし、`cancelled` になった実行は「必須チェックが
  まだ緑になっていない」状態のままなので、後続の実行が終わって `success` を報告するまでの
  短い間、その PR は一時的にマージ不可のままになります。慌てず後続の実行を待ってください。
- **ruleset は自分自身にも適用される。** 管理者であっても、今回の設定では
  ruleset をバイパスするアクター（bypass actor）を指定していないため、`main` への
  直接 push はできません。実際に Step 8 で自分自身の push が拒否されることを確認しました。
  緊急時に管理者だけがバイパスできるようにしたい場合は、ruleset に bypass actor を
  明示的に追加する必要があります（今回は追加していません）。

## 7. 演習課題

以下の3問は `docs/stages/answers/stage-02.md` に解答があります。
まず自分で予想してから答えを見てください。

1. **問1**: `docs/` だけを変更した PR を作り、CI が走ることを確認する。なぜ `pull_request` 側には
   `paths-ignore` を付けていないのか説明する。
2. **問2**: `concurrency` の `group` から `${{ github.ref }}` を消すと何が起きるか予想し、確かめる。
3. **問3**: `ci.yml` のジョブの `name:` を `Lint and Test` に変更して PR を出す。

## 8. 実務への持ち込みメモ

既存リポジトリに必須チェックを入れるときは、いきなり Enforcement status を **Active** に
しないでください。まず **Evaluate**（違反を記録するだけで実際にはブロックしない設定）で
数日〜1週間ほど運用し、既存の PR フローが本当に壊れないか（チェックが必ず報告されるか、
見落としていたブランチ運用がないか）を確認してから Active に切り替える方が安全です。
学習用の1人リポジトリでは影響範囲が自分だけなので今回は最初から Active にしましたが、
チームが使っているリポジトリでは、この慎重さが「入れた瞬間に全員の PR が止まる」事故を防ぎます。
