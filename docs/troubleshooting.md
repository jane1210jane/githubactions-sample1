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

### PR が「Expected — Waiting for status to be reported」から進まない

**原因**: 必須チェックに指定した名前のジョブが、その PR では起動していない。
`paths` / `paths-ignore` フィルタでワークフロー自体がスキップされると、
チェックは「未報告」のまま永久に待ち続ける。
**対処**: `pull_request` トリガーには `paths` フィルタを付けない。
どうしても付けたい場合は、常に成功する集約ジョブを 1 つ用意し、そちらを必須チェックにする
（この設計はモノレポ化する Stage 9 で扱う）。
