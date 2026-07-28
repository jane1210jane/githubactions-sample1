# Stage 1: Python アプリに CI をつける

## 1. このステージのゴール

- `sales-report` アプリに CI ワークフローをつけ、**push のたびに lint とテストが自動で走り、
  壊れたら赤くなる**状態にする。
- 実際に一度 CI を赤くしてから緑に戻し、「CI が壊れたことを教えてくれる」という体験を
  自分の手で確認する。

このステージでゴールにしているのは「CI を書けること」自体ではなく、
「CI が本当に検出してくれる」ことを自分の目で見ることです。

## 2. 前提

- `stage-00` が完了していること（`.github/workflows/hello.yml` が push でも手動でも動く状態）。
- ローカルに `uv` がインストールされていること。本ステージのローカル確認（`uv sync`、
  `uv run pytest` など）はすべて `uv` 経由で行います。
- `src/sales_report/`（CLI と集計ロジック）、`tests/`（pytest のテスト）、`pyproject.toml`、
  `uv.lock` がすでにリポジトリにコミット済みであること。

## 3. なぜ必要か

Stage 0 の `hello.yml` は、`echo` と `ls -la` と `uname -a` しかしていません。
ワークフローが push で起動すること、ログが読めること、ランナーが使い捨てであることは
体験できましたが、CI 本来の価値である「**壊れたことを自動で知る**」はまだ一度も
体験していません。

`sales-report` にはすでにテスト（`tests/test_aggregate.py`、`tests/test_cli.py`）があります。
これをローカルで手動実行するだけなら CI は不要です。CI が要るのは、
「push した瞬間に、誰の手も介さずテストが走り、失敗したら分かる」という自動化そのものに
価値があるからです。Stage 1 ではこれを、わざとコードを壊して確かめます。

## 4. 手順

### Step 1: 使うアクションの最新メジャーバージョンを調べる

```bash
gh api repos/actions/checkout/releases/latest --jq .tag_name
gh api repos/astral-sh/setup-uv/releases/latest --jq .tag_name
```

実行した時点（2026-07-26）の結果は次のとおりでした。

```
v7.0.1
v9.0.0
```

`actions/checkout` と `astral-sh/setup-uv` はどちらも `v<メジャー番号>` という**フロート版タグ**
（メジャーバージョン内の最新パッチへ自動的に追従するタグ）を公開しています。
`actions/checkout` は最新リリース `v7.0.1` に対応する `v7` を、`astral-sh/setup-uv` は
最新リリース `v9.0.0` に対応する `v9` を……公開していそうに見えますが、実際に
`gh api repos/astral-sh/setup-uv/git/matching-refs/tags/v` で確認すると、
`astral-sh/setup-uv` のフロート版タグは `v1`〜`v7` までしか存在せず、`v8`・`v9` はまだ
（完全版タグ `v8.x.y`・`v9.0.0` はあっても）フロート版タグが作られていませんでした。
そのため `ci.yml` では `astral-sh/setup-uv@v7` と、1つ古いメジャー版のフロート版タグを
指定しています。存在しないタグ（`@v9` など）を指定すると `uses:` の解決自体に失敗し
ステップが即座に落ちるため、**「最新リリースのメジャー番号」と「実際に存在するフロート版タグの
メジャー番号」は必ずしも一致しない**ことに注意してください。フロート版タグがどこまで
存在するかは公開側の運用次第で変わるため、実装時は Step 1 のコマンドに加えて
`gh api repos/<owner>/<repo>/git/matching-refs/tags/v` のようなコマンドで実物を
確認する習慣をつけてください。

### Step 2: `ci.yml` を作成する

`.github/workflows/ci.yml` を作成します。`uses:` のバージョンは Step 1 で確認した実際のタグに
合わせてあります。以下は **Stage 1 完了時点（タグ `stage-01`）の内容をそのまま転記したもの**です。
`on:` と `concurrency:` は Stage 2 でトリガー設計ごと書き換えられるため、現在の `main` の
`ci.yml` はこれと異なります（`pull_request:` が追加され、`push:` にブランチ・パスの絞り込みが
入り、`concurrency:` ブロックが新設されています）。本ドキュメント内の行番号の引用
（このステップと次の「5. 何が変わったか」節）は、すべて**この転記ブロック内の行番号**を指しており、
リポジトリの実ファイルを開いて数える必要はありません。

<!-- transcript: .github/workflows/ci.yml @ stage-01 -->
```
  1| # Stage 1: アプリに CI をつける。
  2| # push のたびに lint とテストを走らせ、壊れたことをすぐ知る。
  3| name: CI
  4|
  5| on:
  6|   push:
  7|
  8| permissions:
  9|   contents: read
 10|
 11| jobs:
 12|   test:
 13|     name: Lint & Test
 14|     runs-on: ubuntu-latest
 15|     steps:
 16|       # Stage 0 で見たとおり、ランナーは空。まずリポジトリを持ってくる。
 17|       - name: リポジトリを取得する
 18|         uses: actions/checkout@v7
 19|
 20|       - name: uv と Python をセットアップする
 21|         uses: astral-sh/setup-uv@v7
 22|         with:
 23|           python-version: "3.12"
 24|
 25|       # --locked: uv.lock と pyproject.toml がずれていたら失敗させる。
 26|       # ローカルと CI で違う依存が入る事故を防ぐ。
 27|       - name: 依存関係をインストールする
 28|         run: uv sync --locked
 29|
 30|       - name: フォーマットを確認する
 31|         run: uv run ruff format --check .
 32|
 33|       - name: lint を確認する
 34|         run: uv run ruff check .
 35|
 36|       - name: テストを実行する
 37|         run: uv run pytest -v
```

### Step 3: コミットして push し、CI が緑になることを確認する

```bash
git add .github/workflows/ci.yml
git commit -m "ci: Python の lint とテストを実行するワークフローを追加"
git push
RUN_ID=$(gh run list --workflow=ci.yml --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch "$RUN_ID" --exit-status
```

手元では実際に次の実行が緑になることを確認しました（実行 ID `30221810143`）。

```
✓ main CI · 30221810143
JOBS
✓ Lint & Test in 12s
  ✓ リポジトリを取得する
  ✓ uv と Python をセットアップする
  ✓ 依存関係をインストールする
  ✓ フォーマットを確認する
  ✓ lint を確認する
  ✓ テストを実行する
```

テストログの最終行は `12 passed in 0.10s` でした。

### Step 4: わざと壊して CI が赤くなることを確認する

```bash
sed -i 's/return EXIT_OK/return 1/' src/sales_report/cli.py
git commit -am "test: CI が失敗を検出することを確認する（この後 revert する）"
git push
RUN_ID=$(gh run list --workflow=ci.yml --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch "$RUN_ID" --exit-status   # このステップでは非0終了が正しい結果
```

手元では実際に `テストを実行する` ステップが FAIL し、ジョブ全体が赤くなることを
確認しました（実行 ID `30221834911`）。ログには次のように出ます。

```
FAILED tests/test_cli.py::test_main_prints_monthly_totals_and_returns_zero - assert 1 == 0
========================= 1 failed, 11 passed in 0.09s =========================
##[error]Process completed with exit code 1.
```

### Step 5: 壊した変更を戻し、CI が緑に戻ることを確認する

```bash
git revert --no-edit HEAD
git push
RUN_ID=$(gh run list --workflow=ci.yml --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch "$RUN_ID" --exit-status
```

`git revert` は壊したコミットを打ち消す新しいコミットを作るだけで、履歴からは消しません。
「壊したコミット」と「戻したコミット」の両方が `git log` に残ります。
手元では実際に緑に戻ることを確認しました（実行 ID `30221850262`）。

### Step 6: README にステータスバッジを追記する

`README.md` の見出し `# GitHub Actions 段階学習リポジトリ` の直後に、次の行を追加します。

```markdown
[![CI](https://github.com/jane1210jane/githubactions-sample1/actions/workflows/ci.yml/badge.svg)](https://github.com/jane1210jane/githubactions-sample1/actions/workflows/ci.yml)
```

このバッジ画像は GitHub 側が `ci.yml` という**ワークフローファイル名**をキーにして
最新の実行結果から動的に生成しています。ファイルを手元で用意する必要はありません。

## 5. 何が変わったか

`ci.yml` を書いたことで、以下が具体的な行と対応するようになりました。
以下の行番号は、Step 2 で転記した `ci.yml`（タグ `stage-01` 時点の内容）の行番号です。
`on:` と `concurrency:` は Stage 2 で追加されるため、現在の `main` の `ci.yml` では
これらの行番号がずれています（Stage 2 の解説は `docs/stages/stage-02-triggers-and-pr-gate.md`
を参照してください）。

- **`ci.yml` の `uses:`**（18行目 `uses: actions/checkout@v7`、21行目 `uses: astral-sh/setup-uv@v7`）:
  自分でコマンドを書く `run:` と違い、他人（ここでは GitHub 自身と astral-sh 社）が公開した
  再利用可能な処理（アクション）を呼び出す書き方です。`actions/checkout` はリポジトリの中身を
  ランナーにコピーしてくるアクションで、**Stage 0 で `ls -la` を実行しても何も表示されなかった
  理由がこれです**。Stage 0 のワークフローには `actions/checkout` が無かったため、
  ランナーは本当に空のままでした。
- **`with:`**（22〜23行目）: アクションに渡す引数です。`astral-sh/setup-uv@v7` に対して
  `python-version: "3.12"` を渡し、インストールする Python のバージョンを指定しています。
- **バージョン指定 `@v7`**（18行目・21行目）: `uses:` には必ずバージョンをつけます。
  省略はできません。ここでは `actions/checkout`・`astral-sh/setup-uv` のどちらも、
  メジャー版のフロート版タグ `@v7` を使っています（`astral-sh/setup-uv` については
  Step 1 の解説のとおり、フロート版タグが `v7` までしか存在しないため、最新リリースの
  `v9.0.0` ではなく `v7` を使っている点に注意してください）。コミット SHA まで固定する
  ようなより厳密な指定方法は Stage 6 で扱います。
- **`uv sync --locked`**（28行目）: `--locked` は「`uv.lock` と `pyproject.toml` の内容が
  ずれていたら、ロックファイルを自動更新せずに失敗させる」指定です。これが無いと、
  依存関係がずれていても CI は黙ってロックファイルを更新して先に進んでしまい、
  「ローカルと CI で実際にインストールされる依存が違う」という事故に気づけません。
- **ステップを lint / format / test に分けたこと**（30〜37行目、`フォーマットを確認する`・
  `lint を確認する`・`テストを実行する` の3ステップ）: 1つの `run:` にまとめて
  `ruff format --check . && ruff check . && pytest -v` と書くこともできますが、
  そうすると Actions のログはステップ単位でしか折りたためないため、**どこで落ちたか**を
  確認するのに毎回ログ全体を開く必要が出てきます。ステップを分けておけば、
  赤くなったステップ名を見るだけでフォーマット崩れなのか lint 指摘なのかテスト失敗なのかが
  一目で分かります。

## 6. つまずきポイント

- **症状**: `ModuleNotFoundError: No module named 'sales_report'`。
  **原因**: `actions/checkout` を書き忘れているか、依存のインストール（`uv sync`）より前に
  テストを実行している。Stage 0 で見た「ランナーは空」を思い出してください。

- **症状**: `The lockfile at 'uv.lock' needs to be updated` で `uv sync --locked` が失敗する。
  **原因**: `pyproject.toml` の依存を変更したのに `uv.lock` を更新・コミットし忘れている。
  ロックファイルは必ずコミットしてください。

- **症状**: ログの最後に `Error: Process completed with exit code 1` とだけ出て、
  何が悪いのか分からない。
  **原因**: これは「ステップのコマンドが 0 以外で終了した」という**結果**を報告しているだけで、
  原因そのものではありません。実際に今回の Step 4 のログでも、この行の**直前**に
  `FAILED tests/test_cli.py::...` という具体的な失敗内容が出ています。まずその上を読んでください。

- **症状**: README に貼ったバッジが、成功・失敗にかかわらずずっとグレーの `no status` のまま。
  **原因**: バッジ URL 中のリポジトリ名やワークフローファイル名（`ci.yml`）が実際のものと
  違っている。この失敗はエラーも出さず**無言で壊れる**ため、貼った直後に実際の表示を
  目で確認する習慣をつけてください。

- `uv run sales-report data/sales_sample.csv` の出力が文字化けする → プログラムの不具合ではなく、
  Windows コンソールの文字コードの問題です。対処は README の
  [Windows で進める場合](../../README.md#windows-で進める場合) にまとめてあります。

## 7. 演習課題

以下の3問は `docs/stages/answers/stage-01.md` に解答があります。
まず自分で予想してから答えを見てください。

1. **問1**: `uv sync --locked` を `uv sync` に変えると何が起きるか。`pyproject.toml` に
   依存を1つ足して `uv.lock` を更新せずに push し、挙動の違いを確かめる。
2. **問2**: lint のステップを test の**後ろ**に移すと、開発体験がどう変わるか。
3. **問3**: `data/sales_sample.csv` を CLI にかけた結果をテストに追加する。

## 8. 実務への持ち込みメモ

既存プロジェクトへ CI を後から入れるときは、まず**現状で通るテストだけ**を対象にして
緑を作ることを優先してください。最初から「本当はもっとテストがあるべき」「本当はカバレッジも
測るべき」と全部を一度に通そうとすると、最初の CI 導入そのものが赤いまま止まってしまい、
結局誰も CI の結果を見なくなります。まず緑の状態を作ってチームに定着させ、
そこから少しずつ厳しくしていく方が、遠回りに見えて確実です。
