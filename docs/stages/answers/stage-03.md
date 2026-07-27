# Stage 3 演習課題 解答

[stage-03-speed-and-matrix.md](../stage-03-speed-and-matrix.md) の演習課題3問への解答です。
先に自分で予想してから読んでください。

## 問1: `fail-fast` を既定（`true`）に戻し、`windows-latest` のテストだけをわざと失敗させて、`fail-fast: false` のときと挙動を比べる

**注記**: 問2・問3と異なり、この問1は実際に CI 上で実行して確かめたものではありません。
以下は `strategy.fail-fast` の公開されている仕様に基づく推論です。

**予想**: `fail-fast` は「早く失敗を知る」ための設定に見えるので、`true` に戻しても
「Windows のレグが早く赤くなるだけ」で、大きな違いは無さそうに思うかもしれません。

**解答**: `fail-fast: true`（既定値）にすると、matrix のどれか1つのレグが失敗した瞬間、
GitHub は**残りの matrix レグ（実行中のものだけでなく、ランナー割り当て待ちで
まだ開始していない待機中＝queued のレグも含む）を即座にキャンセル**します。
`windows-latest` のテストだけをわざと失敗させた場合、`ubuntu-latest / 3.12` や
`ubuntu-latest / 3.13` は、実行中であればもちろん、まだ実行が始まっていなくても、
`windows-latest` の失敗を待たずに `cancelled` として打ち切られます。

これが問題になるのは、**キャンセルされたレグの結果が分からなくなる**ことです。
「Windows だけの問題なのか、それとも Python バージョンやコードそのものの問題で、
たまたま Windows が先に落ちただけなのか」を切り分けたいときに、他のレグの結果が
`cancelled`（未検証）になってしまうと、原因調査に必要な情報がキャンセルによって
失われます。CI の目的が単に「壊れたことを知る」ことではなく「**何が**壊れたかを知る」
ことである以上、原因調査の局面では `fail-fast: false` が有利です。

一方で、`fail-fast: true` が不利なわけではありません。1つでも落ちることが分かった時点で
残りの実行を打ち切れば、CI 全体としての消費時間・料金を節約できます。実行時間そのものを
優先したい場面（例えばマージキューのように「1つでも失敗したら即座に次の候補を試したい」
運用）では `true` の方が有利です。本教材の `ci.yml` が `fail-fast: false` を選んでいるのは
（詳しくは [stage-03-speed-and-matrix.md](../stage-03-speed-and-matrix.md) の
「何が変わったか」を参照）、学習の場面では「原因を知る」ことの価値が「早く打ち切る」ことの
価値を上回ると判断したためです。

## 問2: `gate` ジョブの `name:` を `CI Gate` に変えると何が起きるか（実行はせず説明する）

**解答**: ruleset がこのリポジトリの必須チェックとして登録しているのは、ジョブの `jobs:`
キー（`gate`）ではなく、`name:` に書かれた文字列 `Lint & Test` です
（Stage 2 の演習3で確認したとおりです）。`gate.name` を `CI Gate` に変更すると、
ワークフロー自体は変わらず成功し続けますが、GitHub に報告されるチェック名が
`CI Gate` に変わります。その結果、ruleset が待ち続けている `Lint & Test` という名前の
チェックは二度と報告されなくなり、**すべての PR が「必須チェック未報告
（Expected — Waiting for status to be reported）」のままマージ不能になります**。
CI 自体は緑で成功しているにもかかわらず、マージだけができない状態です。

復旧するには、ワークフロー側の `name:` を元に戻すか、ruleset 側の必須チェック名を
`CI Gate` に変更するかのどちらかを、**同時に**行う必要があります。片方だけを直しても、
名前が一致するまではこの状態が続きます。ジョブ名は人間が読みやすくするための
ラベルに見えますが、実際には ruleset との識別子でもあるため、リファクタリングの
ついでに気軽に変えてよい文字列ではありません。この演習は、実際に変更すると
このリポジトリ自身の必須チェックが機能しなくなり後続の作業に支障が出るため、
**実際の変更は行わず**、知識として確認するだけにとどめています。

## 問3: matrix に `python-version: "3.11"` を追加すると何が起きるか

**予想**: matrix に値を1つ足すだけなので、`Test (ubuntu-latest / Python 3.11)` のような
レグが1つ増えて、そのまま緑になりそう、あるいは Windows だけ・Ubuntu だけが落ちそうに
思うかもしれません。

**実際に確かめる**: `matrix.python-version` に `"3.11"` を実際に追加して push しました
（実行 ID `30279340067`）。`matrix.os` は `[ubuntu-latest, windows-latest]` の2つで、
`exclude` が除外しているのは `windows-latest` × `python-version: "3.12"` の組み合わせ
だけです（詳しくは [stage-03-speed-and-matrix.md](../stage-03-speed-and-matrix.md) の
「何が変わったか」を参照）。`"3.11"` はその `exclude` の対象外なので、
`ubuntu-latest` × `3.11` と `windows-latest` × `3.11` の**両方**のレグが生成され、
実際に**両方とも赤くなりました**。

```
X Test (ubuntu-latest / Python 3.11)  in 9s
X Test (windows-latest / Python 3.11) in 16s
```

`ubuntu-latest / Python 3.11` のログに実際に出力されたエラーです。

```
error: The requested interpreter resolved to Python 3.11.15, which is incompatible with the project's Python requirement: `>=3.12` (from `project.requires-python`)
```

`windows-latest / Python 3.11` でも同じ形式のエラーで、パッチバージョンだけが異なりました
（`Python 3.11.9`）。

```
error: The requested interpreter resolved to Python 3.11.9, which is incompatible with the project's Python requirement: `>=3.12` (from `project.requires-python`)
```

**解答**: `pyproject.toml` には次の指定があります。

```toml
[project]
requires-python = ">=3.12"
```

`requires-python = ">=3.12"` という制約は OS に依存しません。`astral-sh/setup-uv` が
Python 3.11 をセットアップした後、`uv sync --locked` がこの制約との矛盾を検出して
失敗するのは、`ubuntu-latest` でも `windows-latest` でも**同じ理由**です。したがって
`fail-fast: false` で他のレグへの巻き添えを防いでいても、赤くなるのは「Ubuntu だけ」でも
「Windows だけ」でもなく、**Python 3.11 の
レグが2つとも**（`Test (ubuntu-latest / Python 3.11)` と `Test (windows-latest / Python 3.11)`）
赤くなります。OS を変えても救われない失敗である、という点が実測から確認できました。

この結果が示しているのは、**matrix は「動かしたい組み合わせ」を書く場所であって、
プロジェクトが対応している範囲そのものを宣言する場所ではない**、ということです。
`pyproject.toml` の `requires-python` が「対応する Python の範囲」の正式な宣言であり、
`ci.yml` の matrix はそれと**一致していなければならない**制約を受ける側です。
両者がズレると、matrix に足しただけの1行で、影響を受けるすべての OS のレグが
一斉に壊れます。逆に、`requires-python` を広げたのに matrix を更新し忘れると、
対応すると宣言した環境の一部を誰も検証しないまま「CI は緑」という状態になり得ます。
matrix と `requires-python` は**セットで**見直す習慣が必要です。確認後は、追加した
`"3.11"` を matrix から削除し（`git revert` で戻しました）、3レグの構成に戻しています。
