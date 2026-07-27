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

### `error: The requested interpreter resolved to Python 3.11.15, which is incompatible with the project's Python requirement: `>=3.12` (from `project.requires-python`)`

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
**対処**: `shell: bash` を付ける。Windows でも動かす必要があるなら `shell: pwsh` を検討する。

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
