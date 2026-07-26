# Stage 1 演習課題 解答

[stage-01-python-ci.md](../stage-01-python-ci.md) の演習課題3問への解答です。
先に自分で予想してから読んでください。

## 問1: `uv sync --locked` を `uv sync` に変えると何が起きるか

**予想**: `--locked` を外しても `uv.lock` の内容が古ければ普通にエラーになりそう、と
思うかもしれません。

**実際に確かめる**: `pyproject.toml` の `dependencies` に依存を1つ足し（例:
`dependencies = ["tomli>=2.0"]`）、`uv.lock` を更新せずに、CI 側だけ一時的に
`uv sync --locked` を `uv sync` に変えて push します。

**解答**: `--locked` が無いと、`uv sync` は `pyproject.toml` とのズレを検出した時点で
**エラーにせず、その場で `uv.lock` を書き換えてから同期を続行**します。手元で実際に
試すと次のようになりました。

```
# --locked あり
$ uv sync --locked
The lockfile at `uv.lock` needs to be updated, but `--locked` was provided.
To update the lockfile, run `uv lock`.
（終了コード 1）

# --locked なし
$ uv sync
Resolved 11 packages in 10ms
 + tomli==2.4.1
（終了コード 0、uv.lock が黙って更新される）
```

つまり `--locked` を外すと CI は**通ってしまいます**。しかしその結果、CI 環境にだけ
新しいロックファイルの内容がインストールされ、手元のロックファイルとはズレたままになります。
これが「自分の環境では動くのに、他の人の環境や本番では動かない」の温床です。
コミットされていない `uv.lock` の変更は誰にも共有されないため、次に誰かが
`uv sync --locked` を使わずに作業すると、また別のロックファイルが生成されかねません。
**`--locked` は必ず付けておき、ズレそのものを CI に検出させる**のが正しい使い方です。

## 問2: lint のステップを test の後ろに移すとどうなるか

**予想**: ステップの順番は最終結果（緑/赤）に影響しないので、どちらでも同じでは、
と思うかもしれません。

**解答**: 最終的にジョブが赤くなるかどうかは同じですが、**赤くなるまでの速さ**が変わります。
`ruff format --check` や `ruff check` は静的な解析なのでほぼ一瞬で終わりますが、
`pytest` はテストの数やデータ量によっては数秒〜数十秒かかることもあります。
lint を先に置いておけば、フォーマット崩れや未使用インポートのような単純なミスは
テストの実行を待たずに数秒で分かります。逆に test を先に置くと、単純な lint 違反ですら
テスト一式が終わるまで気づけません。「速くて壊れやすいものを先に置き、失敗に早く気づく」
という考え方を**フェイルファスト**と呼びます。なお、lint と test を別々のジョブに分けて
並列に実行する、という選択肢もありますが、それによる時間短縮は Stage 3 で扱います。

## 問3: `data/sales_sample.csv` を CLI にかけた結果をテストに追加する

**解答**:

```python
def test_main_processes_the_bundled_sample_file(capsys):
    assert main(["data/sales_sample.csv"]) == EXIT_OK
    assert "2026-03" in capsys.readouterr().out
```

（`pyproject.toml` の `testpaths = ["tests"]` は pytest の収集対象を指定しているだけで、
テストを**実行するときのカレントディレクトリ**はリポジトリルートのままです。
そのため `"data/sales_sample.csv"` という相対パスは、ローカルで `uv run pytest` を
実行したときも、CI の `テストを実行する` ステップで `uv run pytest -v` が
実行されるときも、同じくリポジトリルート基準で解決され、この書き方で動きます。）

実際に上記のテストをローカルに追加して実行し、パスすることを確認しました。

```
tests/test_ex3_check.py::test_main_processes_the_bundled_sample_file PASSED [100%]
============================== 1 passed in 0.06s ==============================
```

（確認用に一時的に追加したファイルで、確認後は削除しています。実際にこのテストを
本採用する場合は `tests/test_cli.py` に追記してください。）
