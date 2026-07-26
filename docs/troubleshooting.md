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
