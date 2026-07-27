# Stage 4 演習課題 解答

[stage-04-quality-gate.md](../stage-04-quality-gate.md) の演習課題3問への解答です。
先に自分で予想してから読んでください。

## 問1: テストを1つ削除すると、カバレッジは閾値（80%）を下回るか

**予想**: このプロジェクトのテストは28件あり、カバレッジは98.26%まで達しています
（`stage-04-quality-gate.md` の手順Bを参照）。閾値は80%なので、余裕は18ポイント以上
あります。「テストを1つ削除すれば数ポイント下がって80%を割るだろう」と予想するのが
自然です。

**実際に確かめる**: 予想が正しいかを確かめるため、既存の28件のテスト**すべて**を、
1つずつ削除してはカバレッジを測定する、という総当たりを行いました。結果は次のとおりです
（一部抜粋。値は削除後の `TOTAL` カバレッジ）。

| 削除したテスト | 削除後のカバレッジ |
|---|---|
| `test_main_reports_a_readable_error_when_a_row_is_truncated`（`tests/test_cli.py`） | 98.26%（変化なし） |
| `test_format_table_states_explicitly_when_there_is_no_data`（`tests/test_aggregate.py`） | 98.26%（変化なし） |
| `test_check_document_reports_a_missing_file`（`tests/test_check_doc_citations.py`） | 97.09% |
| `test_main_returns_one_and_reports_to_stderr_when_a_document_is_broken`（同上） | 96.51%（28件中もっとも下げ幅が大きかった1件） |

**28件のうちどれを1つ削除しても、結果は96.51%〜98.26%の範囲に収まり、80%を割るものは
1件もありませんでした。** 予想は外れました。

**理由**: このプロジェクトのテストには、同じソースコード行を複数のテストが重ねて
実行している箇所が多くあります。たとえば `parse_records` の「必須列が無い」を確認する
テストと、「DictReader が値を `None` で埋める」ケースを確認するテストは、別の入力から
同じ `raise ValueError(...)` の行を通ります（`src/sales_report/aggregate.py`
`_parse_row`）。カバレッジは「その行が**一度でも**実行されたか」しか見ないため、
片方のテストを消してももう片方が同じ行を実行し続け、数字は変わりません。
テストの**本数**は28件でも、行単位のカバレッジという指標から見ると重複が大きく、
「1本削除する」という操作に対して鈍感になっていました。

**閾値を割るところまで確かめる**: `tests/test_check_doc_citations.py` の役割は
`tools/check_doc_citations.py`（102 statements、全体172 statementsの過半）を検証することです。
このファイルの**13個のテスト関数の定義をすべて削除し**（関数の中身だけでなく `def` ごと
削除し）、ファイル先頭の `check_doc_citations` の import 文だけを残す（モジュール自体は
読み込まれるが、どの関数も一度も呼ばれない状態にする）と、初めて閾値を割りました。
このとき pytest が収集するテストは残り2ファイル分の15件（`test_aggregate.py` の11件 +
`test_cli.py` の4件）になり、下のログの `15 passed` はそれと一致しています。

```
$ uv run pytest -q
...............
ERROR: Coverage failure: total of 59 is less than fail-under=80
                                                                         [100%]
=============================== tests coverage ================================
_______________ coverage: platform win32, python 3.14.5-final-0 _______________

Name                            Stmts   Miss  Cover   Missing
-------------------------------------------------------------
src\sales_report\__init__.py        0      0   100%
src\sales_report\aggregate.py      45      0   100%
src\sales_report\cli.py            25      1    96%   44
tools\check_doc_citations.py      102     70    31%   44-49, 54-68, 72-104, 108-119, 123, 127, 136-144, 149-153, 157-163, 167-169, 173
-------------------------------------------------------------
TOTAL                             172     71    59%
FAIL Required test coverage of 80% not reached. Total coverage: 58.72%
15 passed in 0.08s
EXIT=1
```

（この `python 3.14.5-final-0` はこの実験を行ったローカル環境の Python バージョンで、
CI の matrix（3.12 / 3.13、`pyproject.toml` の `requires-python = ">=3.12"`）とは
無関係です。この実験はローカルのみで行い、push はしていません。）

（確認後、`tests/test_check_doc_citations.py` は `git diff` で変更が残っていないことを
確認したうえで元の内容に戻しています。この実験はローカルのみで行い、push はしていません。）

**ログのどこに理由が出ているか**: 上のログのとおり、`FAIL Required test coverage of 80%
not reached. Total coverage: 58.72%` は、pytest 本体のテスト結果（`...............` や
カバレッジ表）が出そろった**直後**、`pytest` 自身の最終行（`15 passed in 0.08s`）の
**直前**に出ます。CI 上でこのコマンドが失敗すると、この行より後に GitHub Actions
ランナー自身が付け足す `Error: Process completed with exit code 1` という行が続きます
（この行は本教材の [トラブルシューティング索引](../../troubleshooting.md) に
すでに載せているとおり、失敗した**結果**を示す表示であって、失敗した**理由**では
ありません）。理由を知りたいときは、この行の**直前**――つまり `FAIL Required test
coverage of 80% not reached.` の行と、その手前のカバレッジ内訳の表（`Missing` 列に
実行されなかった行番号が出ます）を読みます。

**この演習からの教訓**: 「テストを1つ削除すればゲートが落ちる」という前提そのものが、
テストの独立性・重複度に依存します。重複の少ないテストスイートなら1本の削除で
閾値を割れますが、本教材のように行レベルで重複が大きいスイートでは、ゲートを
実際に落とすには「そのモジュールを検証しているテスト群をまとめて削除する」規模の
変更が必要でした。これは弱点というより、**カバレッジという指標が「テストの本数」ではなく
「実行された行の集合」を見ている**ことの裏返しです。

## 問2: `gate` の要約に、失敗したジョブがあるときだけ警告行を足す

**予想**: `contains()` は文字列に対する部分一致検査だと思うと、`needs.*.result` という
配列を渡すのは書き方として誤りに見えるかもしれません。

**解答**:

```yaml
    - name: 失敗を要約に追記する
      if: contains(needs.*.result, 'failure')
      run: echo "> 依存ジョブに失敗があります。上の表を確認してください。" >> "${GITHUB_STEP_SUMMARY}"
```

`contains(search, item)` は GitHub Actions の式では2通りに働きます。`search` が文字列なら
部分一致（`contains('failure-job', 'fail')` は `true`）、`search` が配列なら**要素の完全一致**
（配列の中に `item` と等しい要素が1つでもあれば `true`）です。`needs.*.result` は
`*` フィルターにより「`needs` に列挙した各ジョブの `.result`」を集めた**配列**を返すため、
`contains(needs.*.result, 'failure')` は「依存ジョブのどれか1つでも結果が `failure` である」
という判定として正しく成立します。

**実際に確かめる**: この式が本当に妥当かどうかを、実際にワークフローへ一時的に追加して
確認しました（`stage/04-quality-gate` ブランチ上、実行 ID `30282353016`）。
`tools/check_doc_citations.py` に未使用の `import json` を混ぜて `static` の
「lint を確認する」ステップをわざと失敗させ、`gate` の判定ステップの手前に上記のステップを
挿入して push しました。結果、`Static Checks` が `lint を確認する`（F401 の指摘）で失敗し、
`Lint & Test`（`gate`）ジョブでは新しいステップ「[実験] 失敗を要約に追記する」が
**スキップされずに実行**され、成功しました。ジョブログの `依存ジョブの結果を判定する`
ステップで観測した実際の値は次のとおりです。

```
DEPENDENCY_RESULTS: success failure success
```

（`meta` が success、`static` が failure、`test` が success。matrix の `test` は
3レグまとめて1つの `needs.test.result` に集約されるため、配列の要素数は
`needs` に書いた3ジョブぶんの3個です。）

もし `contains(needs.*.result, 'failure')` が式として不正なら、ワークフロー全体が
**構文解析の時点で** `Invalid workflow file` として弾かれ、1つもジョブが起動しません。
今回はジョブが通常どおり起動し、かつ新しいステップが（スキップではなく）実際に実行
されたので、この式が構文としても意味としても妥当であることを実行結果から確認できました。
確認後、追加したステップと `import json` はどちらも `git revert` で戻し、
`static` を含む全ジョブが緑に戻ることも確認しています。

`contains()` は配列に対しても使える、という点が本問の核心です。`needs.*.result` は
依存ジョブの結果を集めた配列であり、個別のジョブ名を1つずつ `||` でつなぐよりも
短く書けます。

## 問3: `meta` ジョブの `outputs` から `version` を消すと、`gate` のステップサマリはどう表示されるか予想し、確かめる

**予想**: `${{ needs.meta.outputs.version }}` が参照している `version` という出力そのものが
無くなるので、「存在しない値を参照した」として CI がエラーで止まる、と予想するのが
自然に見えます。

**実際に確かめる**: `stage/04-quality-gate` ブランチ上で、`meta` ジョブから
`outputs:` とその次の `version: ${{ steps.read.outputs.version }}` の2行
（[stage-04-quality-gate.md](../stage-04-quality-gate.md) の転記ブロックにある該当箇所）を実際に削除し、
`gate` の「結果をステップサマリに書く」の直後に、`$GITHUB_STEP_SUMMARY` の中身を
そのままログに出す一時的な確認ステップを足して push しました（実行 ID `30282141749`）。

結果は2つとも予想を裏切りました。

1. **CI はエラーで止まりませんでした。** `gate` ジョブの「結果をステップサマリに書く」
   ステップは正常に実行され、ジョブログの `env:` ブロックに実際に記録された値は
   次のとおりでした。

   ```
   env:
     ACTIONLINT_VERSION: 1.7.12
     APP_VERSION: 
     STATIC_RESULT: failure
     TEST_RESULT: success
   ```

   `APP_VERSION: ` の右側が**空**です。`${{ needs.meta.outputs.version }}` は、
   参照先の `outputs.version` が存在しなくても構文エラーにはならず、**空文字列**に
   評価されていました。もしステップサマリの表がそのままレンダリングされていたら、
   「バージョン」の行の値だけが空欄になっていたはずです（表自体は壊れず、
   セルの中身だけが空になります）。
2. **ただし、この push は結果的に CI 全体を落としました。** 理由は `outputs` の
   削除そのものではなく、**同じ実行の中で `Static Checks` ジョブの `ワークフローを
   actionlint で検査する` ステップが実際にこの綴り間違いを検出して失敗した**ためです。
   ログに残った実際の指摘は次のとおりです。

   ```
   .github/workflows/ci.yml:148:28: property "version" is not defined in object type {} [expression]
   148 |           APP_VERSION: ${{ needs.meta.outputs.version }}
       |                            ^~~~~~~~~~~~~~~~~~~~~~~~~~
   ##[error]Process completed with exit code 1.
   ```

   （actionlint が報告した行番号（148）が、[stage-04-quality-gate.md](../stage-04-quality-gate.md)
   の転記ブロックにおける同じ行の番号（149）と1つずれているのは、この実験のために
   `outputs:` の2行を削除した結果、以降の行が1行分ずつ繰り上がっていたためです。
   実験前後で行の中身自体は同じです。）

   `static` が `failure` になった結果、`needs: [meta, static, test]` を持つ `gate` は
   `if: always()` により実行はされましたが（[stage-03-speed-and-matrix.md](../stage-03-speed-and-matrix.md)
   で確認した「`if: always()` が無いと skipped になる」問題はここでは起きていません）、
   最後の「依存ジョブの結果を判定する」ステップが `DEPENDENCY_RESULTS` に `failure` を
   含むことを検出して `exit 1` し、`Lint & Test` チェック自体も失敗として報告されました。

**解答**: エラーにはならず、`${{ needs.meta.outputs.version }}` は空文字列に評価され、
ステップサマリの表では「バージョン」の値が空欄になります（実際に `APP_VERSION: `
が空であることをジョブログの `env:` ブロックで確認済みです）。**存在しないコンテキスト
参照は既定では失敗しない**ため、綴り間違いや消し忘れは、放っておけば無言で空欄になって
現れるだけで、CI が教えてくれるとは限りません。これが Stage 3 で導入した actionlint が
拾ってくれる典型例で、今回も実際に `Static Checks` の actionlint ステップが
`property "version" is not defined in object type {} [expression]` として検出し、
その結果として `gate` も失敗を報告しました。つまり、「値が空欄になる」ことそのものは
actionlint が直接防いでいるわけではなく（実行時評価の話であり、静的検査の対象は
式の妥当性です）、**「存在しない出力を参照している」という綴り間違い自体**を
actionlint が実行前に見つけてくれる、という関係です。actionlint が無ければ、
この間違いは実行時にエラーも起こさず、ステップサマリの空欄という気づきにくい形で
しか現れなかったはずです。

確認後、`outputs:` の2行と一時的な確認ステップは `git revert` で元に戻し、
`static` を含む全ジョブが緑に戻ることを確認しています。
