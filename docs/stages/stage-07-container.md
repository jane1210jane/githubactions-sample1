# Stage 7: ETL 化とコンテナ

## 1. このステージのゴール

`stage-00` から `stage-06` まで、`sales-report` は「その場に Python と `uv` がある」ことを
前提にしか動いてきませんでした。このステージでは、アプリを Lambda コンテナイメージとして
固め、GitHub Container Registry（GHCR）に置き、レイヤキャッシュを自分で設計・管理できる
ようにします。到達点は、実行環境ごとアプリを持ち運べる形にすることと、その持ち運びに
使う CI（`Container` ワークフロー）が自分で作ったキャッシュ機構の効き・限界・
セキュリティ上の境界を、実測をもって説明できることです。

## 2. 前提

- `stage-06` が完了していること。`permissions` の最小化、サードパーティ action の SHA
  ピン留めと Dependabot、`zizmor` によるワークフローの静的検査が導入済みの状態です。

## 3. なぜ必要か

ここまでのアプリは、CLI（`sales-report` コマンド）として人が端末から実行するものでした。
実行するたびに、実行する側の環境に Python 3.12・`uv`・依存パッケージが揃っている必要が
あります。これをデプロイ先（今回は AWS Lambda、`stage-08` で実際に使います）へ持って
いくには、「アプリと、それが動くのに要るものすべて」を1つの実行可能な単位に固める必要が
あります。コンテナイメージはその単位です。加えて、無人で（人が標準出力を読むのではなく）
動かすには、入力を読み、変換し、出力先に書く、という形のプログラムが要ります。これが
`etl.py` を新設した理由です。

## 4. 手順

以下は実際に行った手順です（このドキュメントでは内部の管理番号ではなく実施内容で示します）。

### 手順A: CSV を JSON に集計する ETL モジュールを TDD で実装する

`sales_report.etl` モジュールを、既存の `sales_report.aggregate`（副作用の無い純粋関数群）
を薄くラップする形で追加しました。先にテスト（`tests/test_etl.py`）を書き、
`ModuleNotFoundError: No module named 'sales_report.etl'` で失敗すること（RED）を確認して
から実装し、テストが通ること（GREEN）を確認しています。実装後、テストは42件から47件
（+5）に増え、カバレッジは97.09%から97.29%（`etl.py` 自体は100%）に維持されました。

### 手順B: Dockerfile と `.dockerignore` を書く

Lambda 用のコンテナイメージのベース（`public.ecr.aws/lambda/python:3.12`）を使い、依存の
インストールを先に、アプリ本体のコピーを後に置く2段構成の `Dockerfile` を書きました。
同時に、ビルドコンテキストに含めるべきでないもの（`.git`・`.github`・`.venv`・`docs`・
`htmlcov`・`tests`・`.superpowers`・`__pycache__`・`*.pyc`）を `.dockerignore` に列挙しました。

### 手順C: GHCR へ push するワークフローを追加する

`CI`（検査とテスト）とは別に `Container` ワークフローを新設しました。`docker/setup-buildx-action`
で buildx を用意し、`docker/login-action` で GHCR にログインし、`docker/build-push-action`
でビルドと（条件付きの）push を行う、という1ジョブ構成です。`build` ジョブにだけ
`packages: write` を足し、ワークフロー全体は `contents: read` のままにしています。

### 手順D: レイヤキャッシュを自分で管理する

`Stage 3` では `astral-sh/setup-uv` が Python 依存のキャッシュを自動で面倒みてくれていま
したが、Docker のレイヤキャッシュにはそれに相当する既製の仕組みが無いため、
`actions/cache` を使って自分で保存先ディレクトリと鍵を設計しました。最初の下書きでは
`actions/cache` を1ステップで使っていましたが、`zizmor` が同一ジョブ内に
`actions/cache` と `docker/build-push-action`（publisher とみなされるアクション）が
同居していることを理由に `cache-poisoning`（high severity）を報告したため、
`actions/cache/restore`（常時実行、読み取りのみ）と `actions/cache/save`
（`pull_request` では実行しない）に分割しました。

### 手順E: レビューで見つかった問題を直す

実装後のレビューで、次の3点を修正しました。

1. `uv export` が `--extra aws --no-emit-project` を付けずに実行されると、自分自身
   （`sales-report`）の editable install がレイヤに混入する問題。`pyproject.toml` に
   `[project.optional-dependencies] aws = ["boto3>=1.34"]` を追加し、`uv export` に
   `--extra aws --no-emit-project` を付けて解決しました。
2. キャッシュの鍵を `hashFiles(...)`（内容ハッシュ）にすると、`restore` が完全一致した
   直後に同じ鍵で `save` しようとして失敗し続ける問題。鍵を `github.sha`
   （コミットごとに変わる値）に変更しました。詳しくは次節の実測を参照してください。
3. `tags:` の2つ目の行に無条件で `:latest` を含めていたため、`workflow_dispatch` で
   未マージのブランチから実行すると `:latest` がそのブランチの内容で上書きされてしまう
   問題。`:latest` は `github.ref == 'refs/heads/main'` のときだけ付くように変更しました。

## 5. 何が変わったか

このステージ完了時点（タグ `stage-07`）の `Dockerfile` と `container.yml` を以下に
転記します。行番号引用はすべてこのブロックの行を指します。

`Dockerfile`:

<!-- transcript: Dockerfile @ stage-07 -->
```
1| # Lambda のコンテナイメージ用のベース。Stage 8 でそのまま使えるように
2| # 最初からこれを選んでおく。ローカル実行にも使える。
3| FROM public.ecr.aws/lambda/python:3.12
4| 
5| # 依存の解決だけを先に行う。requirements の内容が変わらない限り、
6| # ここまでのレイヤ（boto3 など aws extra の依存一式）はキャッシュが効く。
7| # --extra aws で Lambda 実行に要る boto3 系を含め、--no-emit-project で
8| # 自分自身（sales-report）の editable install はここでは出さない。
9| # アプリ本体は次の COPY src/ でそのまま配置するので、distribution としての
10| # インストールは不要（Lambda ランタイムが LAMBDA_TASK_ROOT を sys.path に
11| # 加えるため import は通る）。
12| #
13| # boto3 をここで明示的に固定するのは慣習ではなく AWS の公式な推奨事項。
14| # Lambda の Python ランタイムには boto3/botocore が同梱されているが、AWS は
15| # 「ランタイム同梱版に依存せず、boto3 を含む全依存関係を自分のデプロイパッケージに
16| # 含めることを推奨する（ランタイムが同梱版を更新した際のバージョン不整合を防ぐため）」
17| # と明記している。
18| # 参照: https://docs.aws.amazon.com/lambda/latest/dg/python-package.html
19| #   ("Runtime dependencies in Python" - Important 注記)
20| COPY pyproject.toml uv.lock ./
21| RUN pip install --no-cache-dir uv \
22|     && uv export --frozen --no-dev --extra aws --no-emit-project --format requirements-txt > requirements.txt \
23|     && pip install --no-cache-dir -r requirements.txt
24| 
25| # アプリ本体は最後に置く。コードだけ変えたときに再利用できるレイヤを増やすため。
26| COPY src/ "${LAMBDA_TASK_ROOT}/"
27| 
28| CMD ["sales_report.lambda_handler.handler"]
```

`container.yml`（`.github/workflows/container.yml`）:

<!-- transcript: .github/workflows/container.yml @ stage-07 -->
```
1| # Stage 7: アプリをコンテナにして GHCR へ置く。
2| # CI（検査とテスト）とは別のワークフローにしてある。目的が違い、
3| # 走らせたいタイミングも違うため。
4| name: Container
5| 
6| on:
7|   push:
8|     branches: [main]
9|     paths-ignore:
10|       - "docs/**"
11|       - "**/*.md"
12|   pull_request:
13|     branches: [main]
14|   workflow_dispatch:
15| 
16| concurrency:
17|   group: ${{ github.workflow }}-${{ github.ref }}
18|   cancel-in-progress: ${{ github.event_name == 'pull_request' }}
19| 
20| # ワークフロー全体では読み取りだけを許す。GHCR への書き込み権限は
21| # 必要なジョブにだけ足す（Stage 6 で学んだ原則）。
22| permissions:
23|   contents: read
24| 
25| env:
26|   IMAGE_NAME: ghcr.io/${{ github.repository }}/sales-report
27| 
28| jobs:
29|   build:
30|     name: Build & Push
31|     runs-on: ubuntu-latest
32|     timeout-minutes: 20
33|     # GHCR へ push するにはパッケージへの書き込み権限が要る。
34|     # ワークフロー全体ではなくこのジョブだけに足す。
35|     permissions:
36|       contents: read
37|       packages: write
38|     steps:
39|       - name: リポジトリを取得する
40|         uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
41|         with:
42|           persist-credentials: false
43| 
44|       # buildx を使うと、レイヤキャッシュを外部に出し入れできるようになる。
45|       - name: Docker Buildx を用意する
46|         uses: docker/setup-buildx-action@bb05f3f5519dd87d3ba754cc423b652a5edd6d2c  # v4.2.0
47| 
48|       # レイヤキャッシュを actions/cache で自分で管理する。
49|       # Stage 3 では setup-uv がキャッシュを自動で面倒みてくれていたが、
50|       # ここでは保存先と鍵を自分で決める。
51|       #
52|       # 鍵は Dockerfile・依存定義の内容ハッシュ（hashFiles）ではなく、
53|       # github.sha（コミットごとに変わる値）にする。内容ハッシュを鍵にすると、
54|       # 内容が変わらない限り同じ鍵になり、restore が完全一致した直後に
55|       # 同じ鍵で save しようとして「Unable to reserve cache with key ...」で
56|       # 失敗し続ける（actions/cache の鍵は一度書いたら不変で上書きできないため）。
57|       # github.sha にしても、同一コミットに対する2回目の workflow_dispatch や
58|       # re-run では鍵が一致するため、その場合はやはり save が失敗しうる
59|       # （鍵をコミットより細かい粒度にしない限り避けられない制約）。
60|       # 完全一致が無いとき（＝別コミットの初回ビルド）は restore-keys の
61|       # 前方一致で直近のキャッシュから始めるので、再利用性は落ちない。
62|       #
63|       # 復元（restore）と保存（save）を actions/cache/restore と
64|       # actions/cache/save に分けている。ひとまとめの actions/cache はジョブの
65|       # 最後に自動で保存するため、pull_request で走らせても保存が行われる。
66|       # ここでは pull_request では保存しない（下の save ステップの if を参照）。
67|       # ただし GitHub のキャッシュのスコープ規則により、pull_request イベントで
68|       # 作られるキャッシュはマージ先の ref ではなく PR のマージ ref
69|       # （refs/pull/<N>/merge）に閉じており、そもそも push（main）側からは
70|       # 復元できない（公式ドキュメント "Restrictions for accessing a cache":
71|       # 「When a cache is created by a workflow run triggered on a pull
72|       # request, the cache is created for the merge ref ... It cannot be
73|       # restored by the base branch or other pull requests targeting that
74|       # base branch.」）。つまり「PR で汚したキャッシュを push (main) が拾って
75|       # しまう」という経路は、この pull_request イベントに関しては最初から
76|       # 存在しない。
77|       # このワークフローで実際に残っていたのは、同一 ref 上の経路である:
78|       # 同じ PR（同じ merge ref）や同じブランチの run が自分で汚したキャッシュを、
79|       # 後続の「同じ ref 上」の信頼される run が復元してしまう可能性。
80|       # このワークフローは workflow_dispatch でも push: が真になりレジストリへ
81|       # 出すため、これが現実に残っていた経路であり、save を pull_request に
82|       # 限って止めたことの実際の効果はここにある（フォーク越えの経路ではない）。
83|       # それ以外の、実害の無い書き込みを減らす整理（cache-quota の節約、
84|       # 意図の明示）という目的もあるが、脆弱性を塞いだのが主目的ではない。
85|       # zizmor の cache-poisoning
86|       # finding が消えたのも、この if によってではなく actions/cache/restore・
87|       # actions/cache/save が KNOWN_CACHE_AWARE_ACTIONS の "actions/cache"
88|       # （サブパス無しの完全一致）に該当しなくなったため（zizmor のソースで確認済み）
89|       # であり、finding が無いことをリスククラスの解消の証拠にはしない。
90|       - name: レイヤキャッシュを復元する
91|         uses: actions/cache/restore@55cc8345863c7cc4c66a329aec7e433d2d1c52a9  # v6.1.0
92|         with:
93|           path: /tmp/.buildx-cache
94|           key: buildx-${{ runner.os }}-${{ github.sha }}
95|           # 完全一致が無ければ、同じ OS の直近のキャッシュから始める。
96|           restore-keys: |
97|             buildx-${{ runner.os }}-
98| 
99|       - name: GHCR にログインする
100|         if: github.event_name != 'pull_request'
101|         uses: docker/login-action@dbcb813823bdd20940b903addbd779551569679f  # v4.6.0
102|         with:
103|           registry: ghcr.io
104|           username: ${{ github.actor }}
105|           password: ${{ secrets.GITHUB_TOKEN }}
106| 
107|       - name: イメージをビルドする（必要なら push する）
108|         uses: docker/build-push-action@53b7df96c91f9c12dcc8a07bcb9ccacbed38856a  # v7.3.0
109|         with:
110|           context: .
111|           # PR では push しない。フォークからの PR に書き込み権限は渡らないため、
112|           # push しようとすると必ず失敗する。
113|           push: ${{ github.event_name != 'pull_request' }}
114|           # :latest は main への push のときだけ付ける。workflow_dispatch は
115|           # 検証用に任意のブランチから実行できるため、:latest を無条件で
116|           # 付けると未マージのブランチの内容が「最新版」として公開されてしまう。
117|           tags: |
118|             ${{ env.IMAGE_NAME }}:${{ github.sha }}
119|             ${{ (github.ref == 'refs/heads/main') && format('{0}:latest', env.IMAGE_NAME) || '' }}
120|           cache-from: type=local,src=/tmp/.buildx-cache
121|           cache-to: type=local,dest=/tmp/.buildx-cache-new,mode=max
122| 
123|       # cache-to をそのまま同じディレクトリに書くとキャッシュが際限なく育つ。
124|       # 新しいものと入れ替える。
125|       - name: レイヤキャッシュを入れ替える
126|         run: |
127|           rm -rf /tmp/.buildx-cache
128|           mv /tmp/.buildx-cache-new /tmp/.buildx-cache
129| 
130|       # 保存は pull_request では行わない（理由は復元ステップのコメントを参照。
131|       # このワークフローで実際に閉じたのは同一 ref 上の経路であって、
132|       # フォーク越えの脆弱性を塞いだわけではない）。
133|       # 鍵は復元ステップと同じ組み立てにする（github.sha、コミットごとに変わる）。
134|       - name: レイヤキャッシュを保存する
135|         if: github.event_name != 'pull_request'
136|         uses: actions/cache/save@55cc8345863c7cc4c66a329aec7e433d2d1c52a9  # v6.1.0
137|         with:
138|           path: /tmp/.buildx-cache
139|           key: buildx-${{ runner.os }}-${{ github.sha }}
```

- **CLI と ETL の役割の違い** — `cli.py` の `main` は `format_table` の戻り値を
  `print` するだけ、`etl.py` の `run_etl` は同じ集計結果を `to_json_payload` で
  JSON にして `output_path` に書くだけです。どちらも `sales_report.aggregate` の
  `parse_records` / `aggregate_monthly` という副作用の無い純粋関数をそのまま呼ぶ薄い
  ラッパーで、集計ロジック自体（月次集計・行番号つきのエラー）には一切手を加えていません。
  「人が読む出力」と「機械が読む出力」で別の入口を用意し、共通部分は1箇所に閉じ込める、
  という設計のおかげで、コンテナ化のために集計ロジックを書き直す必要がありませんでした。

- **JSON に金額を文字列で入れた理由** — `etl.py` の `to_json_payload` は
  `total.total_amount`（`Decimal`）を `str()` で文字列にしてから JSON に入れています。
  JSON の数値型は仕様上すべて倍精度浮動小数点で表現されるため、`Decimal` の値を
  そのまま数値として書き出すと、読み込み側の実装によっては精度が落ちる可能性があります。
  金額を文字列にしておけば、読み込み側が自分の言語の10進数型（Python の `Decimal` や
  他言語の decimal 型）に変換する余地を残せます。

- **Dockerfile のレイヤ順序** — `Dockerfile` の20〜23行目（依存のインストール）を
  26行目（`COPY src/`）より前に置いています。Docker のレイヤキャッシュは
  「その層とそれ以前の層すべて」が変わっていないときだけ効くため、変わりにくいもの
  （依存定義）を先に、変わりやすいもの（アプリのコード）を後に置くと、コードだけを
  変更したコミットでも依存インストールの層（`Dockerfile` 20〜23行目）を再利用できます。
  逆に置くと何が起きるかは、演習1で実測しています。

- **`CMD` が参照する Lambda ハンドラ** — `Dockerfile` 28行目の
  `CMD ["sales_report.lambda_handler.handler"]` が指す `sales_report.lambda_handler`
  モジュールは、このステージの時点ではまだ存在しません（別のステージで追加します）。
  `CMD` はイメージの起動時に評価される命令であり、ビルド時には一切参照されないため、
  ハンドラが存在しなくてもビルド自体は問題なく完走します。実際に、ハンドラ不在のまま
  ビルドした run のログを確認したところ、`COPY src/` から `RUN pip install` まで
  すべて正常に完了し、ビルドはエラー無く成功しました。**この時点のイメージは
  ビルドできても起動はできません。**

- **`Container` を `CI` と別ワークフローにした理由** — `container.yml` 4行目の
  `name: Container` は、`ci.yml`（検査とテスト）とは独立したワークフローです。
  目的が違う（一方は「壊れていないか」、もう一方は「持ち運べる形にできるか」）だけで
  なく、走らせたいタイミングも違います。`container.yml` 6〜14行目のとおり、`Container`
  は `push`（`main` のみ）・`pull_request`・`workflow_dispatch` の3つのイベントで
  動きますが、ビルドに20分（`container.yml` 32行目の `timeout-minutes: 20`）かかる
  可能性を毎回 `CI` に同居させると、検査とテストという速いフィードバックが必要な処理を
  待たせてしまいます。

- **`packages: write` を足した理由** — `container.yml` の20〜23行目でワークフロー
  全体は `contents: read` のままにし、GHCR へ push する `build` ジョブ（`container.yml`
  29行目）にだけ35〜37行目で `packages: write` を足しています。これは Stage 6 で
  確立した原則（ワークフロー全体に効く権限と、特定のジョブだけが必要とする権限を
  区別し、後者はジョブ側の `permissions:` に書く）をそのまま適用した例です。

- **PR では push しない理由** — `container.yml` の113行目
  `push: ${{ github.event_name != 'pull_request' }}` により、`pull_request` イベント
  では push しません。フォークからの PR には書き込み権限つきトークンが渡らないため、
  push を試みれば失敗しますが、それだけが理由ではなく、レビュー前の内容を
  レジストリに公開しないという意図もあります（演習3で詳しく扱います）。

- **`key` と `restore-keys` の使い分け** — `container.yml` の94行目の `key:` は
  完全一致にしか使えません。一致するキャッシュが無ければ、96〜97行目の
  `restore-keys:` が前方一致で直近のキャッシュを探し、無ければ空のまま処理を続けます
  （`fail-on-cache-miss` を明示的に `true` にしていないため、失敗にはなりません）。
  Stage 3 の `astral-sh/setup-uv` は、これと同等のことを `uv.lock` の内容ハッシュを
  鍵にして自動でやっていました。ここでは Docker のレイヤに対して、同じ発想を
  自分で組み立てています。

- **`cache-to` を別ディレクトリに書いて入れ替える理由** — `container.yml` の120〜121行目
  で、読み込み元（`cache-from: type=local,src=/tmp/.buildx-cache`）と書き込み先
  （`cache-to: type=local,dest=/tmp/.buildx-cache-new,mode=max`）を別ディレクトリに
  しています。同じディレクトリに書くと、読み込み中のキャッシュに書き込みが競合したり、
  古い内容が消えないまま際限なく育ったりします。125〜128行目の
  「レイヤキャッシュを入れ替える」ステップで、ビルド後に新しいキャッシュへ丸ごと
  入れ替えています。

- **実測したキャッシュの効き** — 依存を `--extra aws` で固定した後の構成で、
  異なるコミットに対して `workflow_dispatch` を2回実行し、`container.yml` の
  「レイヤキャッシュを復元する」ステップと「イメージをビルドする（必要なら push
  する）」ステップの所要時間を比較しました。1回目（run `30500023814`、コミット
  `adea9a1`）はジョブ合計35秒・ビルドステップ18秒・復元2秒で、3層とも新規に実行され
  ました。2回目（run `30500085311`、コミット `c0baa52`、空コミットで異なる `github.sha`）
  はジョブ合計25秒・ビルドステップ10秒・復元1秒で、`Dockerfile` の3層
  （`COPY pyproject.toml uv.lock ./` / `RUN pip install ...` / `COPY src/`）すべてが
  `CACHED` になりました。両方とも `save` は成功しており（`Failed to save` は出て
  いません）、キャッシュのサイズはおよそ217MBでした。

## 6. つまずきポイント

- **`.dockerignore` を書かないとビルドコンテキストが巨大になる** — `docker build`
  はビルドコンテキスト（`context: .` で指定したディレクトリ全体）を Docker デーモンへ
  送ってからビルドを始めます。`.venv`・`.git`・`htmlcov` のようなディレクトリを
  除外しないと、コンテキストの転送だけで時間がかかり、意図しないファイル
  （場合によっては認証情報や大きな中間生成物）までイメージに混入するリスクもあります。
  このリポジトリの `.dockerignore` は `.git`・`.github`・`.venv`・`docs`・`htmlcov`・
  `tests`・`.superpowers`・`**/__pycache__`・`*.pyc` を除外しています。

- **`${{ }}` を `run:` に書かない原則は `with:` には適用されない** — Stage 6 では
  「信頼できない値を `run:` の中に直接埋め込まない」ことを学びましたが、これは
  シェルが文字列をコードとして解釈することが原因でした。`with:` はアクションへの
  入力を渡すための構文で、シェルを経由しません。実際に `container.yml` の113行目
  `push: ${{ github.event_name != 'pull_request' }}` や117〜119行目の `tags:` は
  `${{ }}` をそのまま `with:` の値として使っており、これは安全です（`github.event_name`
  や `github.ref` はどちらも外部から自由に書き換えられる値ではありません）。

- **`Container` は必須チェックではない** — ruleset の `required_status_checks` は
  `Lint & Test` のみで、`Build & Push`（`container.yml` の `build` ジョブの `name:`）
  は含まれていません。つまり `Container` が失敗していても PR はマージできます。
  コンテナ化を主目的としつつ、CI のゲートは検査とテストに限定したままにする、
  という設計判断です。ビルドが壊れていることに気づかないままマージしてしまう
  リスクとのトレードオフで、Stage 8 以降で実際にデプロイする段になれば、
  `Container` も必須チェックに含めるかどうかを見直す価値があります。

- **GHCR のパッケージの可視性は、確認するまで分からない** — GitHub 公式ドキュメント
  （`configuring-a-packages-access-control-and-visibility`）には「最初にパッケージを
  公開したとき、既定の可視性は private」という記述があります。ところが、実際に
  このリポジトリの GHCR パッケージ（`ghcr.io/jane1210jane/githubactions-sample1/
  sales-report`）を匿名トークンで確認したところ、`tags/list` と `manifests/latest`
  の両方が認証無しで取得でき、**実際には public でした。** ドキュメントの一般的な
  既定値の記述と、このリポジトリで実際に観測した状態が一致しなかったということ
  自体が教訓です。可視性がどちらであるかは、ドキュメントの一般論を鵜呑みにせず、
  `docker/token`（匿名トークン発行）経由で実際に `tags/list` を叩いて確認してください
  （このリポジトリでの確認コマンドは演習3の解答に載せています）。

- **キャッシュ鍵に内容ハッシュを使うと `save` が壊れる** — 最初の実装では
  `container.yml` の鍵に `hashFiles('Dockerfile', 'uv.lock', 'pyproject.toml')` を
  使っていました。内容が変わらない限り毎回同じ鍵になるため、`restore` が完全一致で
  復元した直後に同じ鍵で `save` しようとして
  `Failed to save: Unable to reserve cache with key ..., another job may be creating
  this cache.` で失敗し続けました。詳しい経緯と実測は演習2の解答を参照してください。

- **`zizmor` は同一ジョブ内のキャッシュ関連アクションと publisher アクションの同居を
  `cache-poisoning` として検出する** — 最初の下書きは `actions/cache`（1ステップ）
  と `docker/build-push-action` を同じジョブに置いていたため、`zizmor` が
  `cache-poisoning`（high severity）を報告しました。`actions/cache` を
  `actions/cache/restore` と `actions/cache/save` に分割したところ、指摘が消えました。
  **ただし、これは `if:` 条件で `pull_request` を除外したから消えたのではありません。**
  `zizmor` はステップの `if:` 条件を評価しないため、ゲートの有無に関わらず対象
  アクションが同一ジョブにあれば検出します。実際に消えた理由は、`zizmor` が
  キャッシュ対応アクションとして認識するリストが `actions/cache`（サブパス無しの
  完全一致）だけを含み、`actions/cache/restore` や `actions/cache/save`
  （同じリポジトリのサブディレクトリ参照）はこの完全一致パターンに当てはまらなく
  なったためです。**つまり `cache-poisoning` というリスククラス自体が無くなった
  わけではなく、静的解析のパターンマッチが対象から外れただけです。** finding が
  ゼロになったことを「解決した」証拠として扱わないよう注意してください。

## 7. 演習課題

以下の3問は [docs/stages/answers/stage-07.md](answers/stage-07.md) に解答があります。
まず自分で予想してから答えを見てください。

1. **問1**: `Dockerfile` の `COPY src/` を依存インストールより**前**に移すと、コードだけ
   変えたときのビルド時間はどうなるか。予想してから実際に試す。
2. **問2**: `actions/cache` の `key` を内容ハッシュ（`hashFiles('Dockerfile', 'uv.lock',
   'pyproject.toml')`）に戻すと何が起きるか。
3. **問3**: `container.yml` の `pull_request` イベントで `push: true` にすると何が起きるか
   予想する。フォークからの PR では実際に失敗するが、自分のブランチからの PR では
   成功してしまう。この差がなぜ生まれるかを説明する。

## 8. 実務への持ち込みメモ

`Dockerfile` のレイヤ順序を決めるときの基準は「変わりにくいものを下に（先に）、
変わりやすいものを上に（後に）」です。依存定義（`pyproject.toml` / `uv.lock`）は
アプリのコードよりずっと変更頻度が低いので、下に置けば、コードだけを直した
コミットのたびに依存を再インストールせずに済みます。キャッシュの鍵を設計するときも
同じ基準で考えてください。「何が変わったら、このキャッシュを作り直すべきか」を
先に決め、その粒度（コミットごとか、依存定義の内容ごとか、OS ごとか）を鍵に
反映します。粒度を粗くしすぎると変更を見逃し、細かくしすぎると（今回の
`hashFiles` の例のように）`restore` と `save` が同じ鍵で衝突して壊れることが
あるので、実際に2回ビルドしてキャッシュが狙いどおりに効く・作り直されることを
確認してから本番の運用に載せてください。
