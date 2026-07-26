# Stage 0 演習課題 解答

[stage-00-first-workflow.md](../stage-00-first-workflow.md) の演習課題3問への解答です。
先に自分で予想してから読んでください。

## 問1: 現在の GitHub リポジトリ名を表示するステップを足す

`greet` ジョブに、次のようなステップを追加すれば表示できます。

```yaml
      - name: リポジトリ名を表示する
        run: echo "$GITHUB_REPOSITORY"
```

`GITHUB_REPOSITORY` のような `GITHUB_*` で始まる環境変数は、GitHub Actions がランナー起動時に
自動的にセットしてくれるもので、自分で `env:` に定義しなくても最初から使えます
（`owner/repo` の形式、例: `jane1210jane/githubactions-sample1`）。

## 問2: `check-isolation` から `needs: greet` を外すと何が起きるか

**予想**: `needs: greet` は「実行順序」を指定しているだけに見えるので、外しても
`check-isolation` は `greet` の後に実行される……と誤解しがちです。

**実際に外して確かめる**:

```yaml
  check-isolation:
    name: 別ジョブから同じファイルを探す
    runs-on: ubuntu-latest
    # needs: greet を外した
    steps:
      - name: 別ジョブに evidence.txt が存在しないことを確認する
        run: |
          if [ -f evidence.txt ]; then
            echo "見つかってしまった（想定外）"
            exit 1
          fi
          echo "存在しない。ジョブごとにランナーは別のマシンである。"
```

**解答**: `needs:` を外すと、`greet` と `check-isolation` は**同時に**走り出します。
Actions タブでそれぞれのジョブの開始時刻・ログのタイムスタンプを見ると、ほぼ同じ時刻に
両方とも "Set up job" が始まっていることで確認できます。

`needs:` はジョブの実行「順序」を書くための機能ではなく、ジョブ間の**依存関係**
（＝このジョブはあのジョブの完了を待つ）を宣言するための機能です。書かなければ、
GitHub は「依存関係が無い＝並列に実行してよい」と解釈します。今回のワークフローでは
`check-isolation` が `greet` の後片付け結果を見る必要があるため、`needs: greet` が必須です。

## 問3: わざとステップを失敗させる

**予想**: `run: exit 1` を書いたステップの後に続くステップはどうなるか。

**実際に確かめる**（`greet` ジョブの好きなステップの直後に挿入）:

```yaml
      - name: わざと失敗させる
        run: exit 1

      - name: ここは実行されるか
        run: echo "この行が実行されればここに出るはず"
```

**解答**: `exit 1` を書いたステップが失敗した時点で、そのジョブは**そこで中断**します。
「ここは実行されるか」ステップは実行されず、Actions タブ上ではスキップ扱いになり、
ジョブ全体の結果も赤い ✗（失敗）になります。既定の挙動では、1つのステップの失敗が
ジョブ全体の失敗に直結します。

もし「あるステップが失敗しても後続のステップは続けたい」という場合は、
そのステップに `continue-on-error: true` を付けます。この使いどころは Stage 4 で扱います。
