# Stage 7 演習課題 解答

[stage-07-container.md](../stage-07-container.md) の演習課題3問への解答です。
先に自分で予想してから読んでください。

## 問1: `COPY src/` を依存インストールより前に移すと、コードだけ変えたときのビルド時間はどうなるか

**予想**: `Dockerfile` のレイヤキャッシュは「その層とそれ以前の層すべてが変わって
いないとき」だけ効きます。依存のインストールより前に `COPY src/` を置くと、依存の
インストール層がコードのコピー層より**後**になるため、コードを1文字でも変えれば
依存インストール層も含めて後続がすべて作り直しになるはずです。つまり、コードだけの
変更でも毎回フルの依存インストールが走るようになり、意図とは逆に「一番効かせたい
依存キャッシュ」を自分で壊すことになるはずです。

**実際に確かめる**: `stage/07-container` ブランチ上で一時的に `Dockerfile` を次のように
変更しました（`COPY src/` を依存インストールより前に移動、commit `e59863c`）。

```dockerfile
FROM public.ecr.aws/lambda/python:3.12

COPY src/ "${LAMBDA_TASK_ROOT}/"

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv \
    && uv export --frozen --no-dev --extra aws --no-emit-project --format requirements-txt > requirements.txt \
    && pip install --no-cache-dir -r requirements.txt

CMD ["sales_report.lambda_handler.handler"]
```

`workflow_dispatch` で1回目のビルドを実行しました（run `30501322151`）。

```
レイヤキャッシュを復元する: Cache restored from key: buildx-Linux-c0baa524a93b6591a476f4813f22c3ad8e476403
  (前のコミットのキャッシュに restore-keys の前方一致でヒット、Cache Size: ~217 MB)
#7 [2/4] COPY src/ /var/task/
#8 [3/4] COPY pyproject.toml uv.lock ./
#9 [4/4] RUN pip install ...
```

ログ中に `CACHED` は1件も出ませんでした（`Dockerfile` の並び自体が変わったため、
復元したキャッシュのどの層とも一致しなかったことによる、当然の全ミス）。
ジョブ合計 **57秒**、ビルドステップ（`docker/build-push-action`）**28秒**
（00:00:54〜00:01:22）でした。

続けて、`Dockerfile` の並びはそのままに、`src/sales_report/etl.py` の docstring に
1行コメントを足すだけの無害な変更を加え（commit `4d95344`）、再度 `workflow_dispatch`
で2回目のビルドを実行しました（run `30501432966`）。

```
レイヤキャッシュを復元する: Cache restored from key: buildx-Linux-e59863c1ad6548ec4161529a4e9a6e12f8617566
  (1回目が保存したキャッシュに完全一致、Cache Size: ~217 MB)
#7 [2/4] COPY src/ /var/task/
#8 [3/4] COPY pyproject.toml uv.lock ./
#9 [4/4] RUN pip install ...
```

**`src/` 配下をコメント1行変えただけにもかかわらず、ここでも `CACHED` は1件も
出ませんでした。** `COPY src/` の層（今回の並びでは2番目の層）が変わったことで、
その後ろに続く依存インストールの層（`COPY pyproject.toml uv.lock ./` と
`RUN pip install ...`）まで巻き添えで作り直しになっています。ビルドステップは
**20秒**（00:02:54〜00:03:14）で、実際に `RUN pip install ... uv export ...` から
`pip install -r requirements.txt` までがフルで再実行されました。

比較のため、正しい順序（依存を先、コードを後）で撮った直近の実測
（[stage-07-container.md](../stage-07-container.md) の「実測したキャッシュの効き」、
run `30500085311`）では、コードは変えず依存定義だけ変わらない状態で
ビルドステップは**10秒**、`COPY pyproject.toml uv.lock ./` と `RUN pip install ...`
の両方が `CACHED` になっています。

**予想どおりの結果でした。** `COPY src/` を依存インストールより前に置くと、
コードだけの変更でも依存インストールの層が巻き添えで無効化され、正しい順序なら
`CACHED` になったはずの層（今回の比較では10秒 対 20秒、差は主に `pip install`
のフル実行分）が毎回作り直しになります。依存が今回よりずっと大きいプロジェクトでは、
この差はさらに開きます。

確認後、`Dockerfile` と `src/sales_report/etl.py` の両方を
`git revert --no-edit 4d95344 e59863c`（commit `67b79f5`・`326a3d0`）で完全に戻し、
`git diff ef4d7ab -- Dockerfile src/sales_report/etl.py` が無出力（差分ゼロ）である
ことを確認しました。`gh pr checks 24` で全チェックが green に戻ったことも確認済みです。

## 問2: `actions/cache` の `key` を内容ハッシュに戻すと何が起きるか

**この問いは brief 作成時点の想定と現在の実装がずれていたため、内容を読み替えています。**
`stage-07` の `container.yml` は当初から `hashFiles('uv.lock')` の一部だけを鍵に
使っていたわけではなく、鍵の設計自体がレビューを経て `github.sha`（コミットごとに
変わる値）に変更されています。したがってここでは「鍵を `hashFiles('uv.lock')` から
外すと何が起きるか」ではなく、**「鍵を `github.sha` から内容ハッシュ
（`hashFiles('Dockerfile', 'uv.lock', 'pyproject.toml')`）に戻すと何が起きるか」**
を扱います。

**今回はこの実験を再実行せず、実装過程で実際に踏んだ実測（既存の run）を証跡として
使います。** `container.yml` はレビュー前の版で実際にこの内容ハッシュ鍵を使っており
（commit `80dc010` の版、`restore` と `save` 両方の `key:` が
`buildx-${{ runner.os }}-${{ hashFiles('Dockerfile', 'uv.lock', 'pyproject.toml') }}`）、
この版のまま `workflow_dispatch` を連続で2回実行したところ、2回目の run
`30468938368` で次のとおり `save` が失敗しました。

```
レイヤキャッシュを復元する:
  restore-keys: buildx-Linux-
  Cache Size: ~202 MB (211989601 B)
  Cache restored successfully
  Cache restored from key: buildx-Linux-f56093788ba364c35966237f7193c738c25e3b43192d4d5f077b05d3ccd4a25c

レイヤキャッシュを保存する:
  Failed to save: Unable to reserve cache with key buildx-Linux-f56093788ba364c35966237f7193c738c25e3b43192d4d5f077b05d3ccd4a25c, another job may be creating this cache.
```

**予想**: 内容ハッシュを鍵にすると、`Dockerfile` と依存定義（`uv.lock` /
`pyproject.toml`）が変わらない限り、毎回同じ鍵になります。1回目の実行で `restore`
が完全一致し（内容が変わっていなければ前回と同じ鍵の内容がそのまま復元される）、
ビルド後に `save` を同じ鍵で試みると、`actions/cache` の鍵は一度書き込んだら
不変で上書きできない仕様のため、「その鍵はもう存在する」という理由で保存に
失敗するはずです。

**実測との一致**: 上記の run `30468938368` はまさにこの経路をたどっています。
1回目の `workflow_dispatch`（run `30468825561`）で鍵
`buildx-Linux-f56093788ba364c35966237f7193c738c25e3b43192d4d5f077b05d3ccd4a25c`
が保存され、`Dockerfile` も依存定義も変えないまま2回目の `workflow_dispatch`
を実行したところ、`restore` は同じ鍵に完全一致し、その直後の `save` が
`Failed to save: Unable to reserve cache with key ...` で失敗しました。予想どおりの
結果です。**しかも、この失敗は3回目以降も再現し続けます。** 内容が変わらない限り
鍵も変わらず、`actions/cache` の鍵は一度書いたら不変なので、このリポジトリの
内容ハッシュ鍵は「最初に保存した内容のまま、二度と更新されない」状態に凍結されます。

さらに、`github.sha` に変更した後の設計にも限界が残っていることを付け加えておきます。
`github.sha` は「コミットごと」にしか変わらないため、**同一コミットに対する2回目の
`workflow_dispatch` や re-run では鍵が一致し、`save` が同じ理由で失敗しうります。**
`container.yml` の鍵設計（コミットごとの粒度）は、内容ハッシュより実用上の失敗頻度を
大きく下げますが、「鍵が一致する可能性」自体を完全には無くしていません。

**解答**: 鍵に内容ハッシュ（`hashFiles(...)`）を使うと、対象ファイルの内容が変わらない
限り同じ鍵になり続けます。`actions/cache` の鍵は一度書き込むと不変で上書きできない
ため、`restore` が完全一致した直後に同じ鍵で `save` しようとすると
`Unable to reserve cache with key ...` で必ず失敗します。これは一時的な不具合ではなく、
**内容が変わらない限り毎回起こる恒久的な失敗**です。`github.sha` のように
コミットごとに変わる値を鍵にすれば、通常は毎コミットで新しい鍵になるため
`save` は成功しますが、同一コミットに対する再実行では同じ問題が再現しうる、という
制約は残ります。

## 問3: `pull_request` で `push: true` にすると何が起きるか

**予想**: `container.yml` の `push:` は現状 `${{ github.event_name != 'pull_request' }}`
になっています。これを無条件の `true` に変えた場合、GitHub の `pull_request`
イベントに対する `GITHUB_TOKEN` の扱いが、PR の出どころによって異なるため、
結果も変わるはずです。

- **フォークからの PR**: GitHub 公式ドキュメント
  （`securely-using-pull_request_target`）に「`pull_request` イベントは
  restricts these events to a read-only `GITHUB_TOKEN`, withholds access to
  other secrets」と明記されています。フォークからの PR に対して発行される
  `GITHUB_TOKEN` は読み取り専用に制限されるため、`build` ジョブの `permissions:`
  ブロックで `packages: write` を宣言していても、実際にフォークの PR で走った
  ジョブに渡るトークンはその宣言どおりの権限を持たず、GHCR への push
  （書き込み）は認証エラーで失敗するはずです。
- **同一リポジトリのブランチからの PR**: フォークを経由しない PR（このリポジトリの
  ブランチ同士の PR、たとえば PR #24 のような `stage/07-container` → `main`）は、
  上記の「読み取り専用に制限される」対象ではありません。`GITHUB_TOKEN` は
  ワークフロー・ジョブに宣言された `permissions:`（`packages: write` を含む）
  どおりの権限を持つため、`docker/login-action` のログインも
  `docker/build-push-action` の push も成功してしまうはずです。

**この差が生まれる理由**: GitHub は「信頼できないコードが混ざりうるフォークからの
PR」と「リポジトリの正規のコラボレーターが作った、フォークを経由しない PR」を
区別して `GITHUB_TOKEN` の権限を決めています。フォークからの PR は、PR の中身
そのもの（コードやワークフロー定義の変更）を信頼できないため、`pull_request`
イベントであっても書き込み権限や `secrets`（`GITHUB_TOKEN` 以外）へのアクセスを
絞ります。一方、フォークを経由しない PR は同じリポジトリの権限を持つ人が作った
ブランチであるため、この制限の対象外です。**つまり「PR だから安全」ではなく
「フォークだから安全」という区別であり、`push: true` を PR で使うと、フォークからは
失敗しますが、フォークを経由しない社内・自分のブランチからの PR では、レビューを
経る前に GHCR へ実際に push されてしまいます。** `container.yml` が `push:` を
`github.event_name != 'pull_request'` で止めているのは、この「フォークかどうか」に
依存しない、より単純で確実な境界（`pull_request` イベントそのものでは push を
一切試みない）を選んだ結果です。

**実際に試すかどうかは任意です。今回は試していません。** 理由は、このリポジトリで
実際に `push: true` を試すには、`pull_request` イベントで GHCR へ push が成立する
状態を一時的に作ることになり、（フォークを経由しない検証である以上）レビュー前の
内容が実際に GHCR へ公開される、という本演習が説明している副作用をそのまま
実環境で発生させることになるため見送りました。上記の予測は、Stage 6 で確認した
「フォークからの PR には書き込み権限つきトークンも `secrets` も渡らない」という
既知の挙動と、GitHub 公式ドキュメントの記述から導いたものです。
