# Stage 8: AWS へ実デプロイ

## 1. このステージのゴール

`stage-07` でコンテナイメージはできましたが、置き場所（GHCR）から先へは進んでいません
でした。このステージでは、そのイメージを実際に AWS 上で動く状態にします。到達点は3つ
です。第一に、**長期のアクセスキーをリポジトリに1つも置かずに** AWS へデプロイできること。
第二に、`staging` へ出してから `production` へ出すまでの間に**人の承認が必ず挟まる**
状態にすること。第三に、壊れたものを出してしまったときに**元のバージョンへ戻せる**手段を、
最初のデプロイと同時に用意しておくことです。

## 2. 前提

- `stage-07` が完了していること。
- [docs/aws-bootstrap.md](../aws-bootstrap.md) の準備（OIDC プロバイダ、デプロイ用ロール、
  Lambda 実行ロール、ECR リポジトリ、S3 バケット、ロールへの権限付与）が済んでいること。
  この準備だけは学習者が手作業で行います。理由は手順書の冒頭に書いてあります。

## 3. なぜ必要か

CI から AWS に入る方法として真っ先に思いつくのは、IAM ユーザーを作ってアクセスキーを
発行し、それをリポジトリのシークレットに置くことです。これは動きます。動きますが、
**その鍵は「誰かが取り消すまで有効」であり、漏れたときに取り返しがつきません。** ログに
出てしまった、フォークに持ち出された、退職者の手元に残った——どれも起こりえます。しかも
漏れたことに気づく手段が基本的にありません。

OIDC（OpenID Connect）はこの前提を変えます。GitHub は**ワークフローの実行ごとに**署名付きの
短命なトークンを発行し、AWS はそのトークンの中身（どのリポジトリの、どのブランチの、
どの環境の実行か）を検証してから、その実行のためだけの一時的な認証情報を貸します。
保存する鍵が無いので、漏れる鍵がありません。

## 4. 手順

以下は実際に行った手順です。

### 手順A: ブートストラップの結果をリポジトリに設定する

学習者が手順書に従って作成した AWS 資源のうち、GitHub 側が知る必要のある4つの値を設定
しました。

| 名前 | 種類 | 値 |
|---|---|---|
| `AWS_ROLE_ARN` | シークレット | デプロイ用ロールの ARN |
| `AWS_REGION` | 変数 | `ap-northeast-1` |
| `ECR_REPOSITORY` | 変数 | `sales-report` |
| `LAMBDA_FUNCTION_NAME` | 変数 | `sales-report-etl` |

ロール ARN だけをシークレットにしているのは、**ARN に AWS アカウント ID が含まれる**ため
です。このリポジトリは public なので、変数にするとワークフローのログにそのまま出ます。
シークレットにすればログでは `***` にマスクされます。残りの3つは秘密ではないので変数に
しています（変数はログに平文で出ますが、`sales-report` という文字列が読まれて困ることは
ありません）。

### 手順B: environments を作る

`staging` と `production` の2つの environment を作り、`production` にだけ承認者を設定
しました。承認者が自分自身であっても、**デプロイの前に一度手を止める仕組みが入ること
自体に意味があります。**

さらに、両方の environment に対して**デプロイ可能ブランチを `main` のみ**に限定しました。
これが必要な理由は手順Dで説明します。

### 手順C: `deploy.yml` を書く

`build`（ECR へ push）→ `deploy-staging` → `deploy-production` の3ジョブ構成のワークフロー
を追加しました。すべての `uses:` は Stage 6 で学んだとおり SHA でピン留めしています。
`zizmor` は指摘なしです。

### 手順D: 信頼ポリシーの `sub` 不一致を修正する

最初の実デプロイ（実行 30563365866）は途中で失敗しました。**`build` は成功し、
`deploy-staging` だけが落ちる**という結果です。

```
Could not assume role with OIDC: Not authorized to perform sts:AssumeRoleWithWebIdentity
```

原因は、`environment:` を指定したジョブが発行させる OIDC トークンの `sub` クレームが、
ref 形式ではなく `<prefix>:environment:<環境名>` になることでした。ブートストラップ
手順書は `<prefix>:ref:refs/heads/main` の1つしか許可していなかったため、environment を
持たない `build` だけが一致し、残る2ジョブが拒否されたわけです。

修正は信頼ポリシー側で行いました。**`sub` を `*` で緩めて回避することはしていません。**
許可するのは次の3つだけです。

| ジョブ | `environment:` | 発行される `sub` |
|---|---|---|
| `build` | 無し | `<prefix>:ref:refs/heads/main` |
| `deploy-staging` | `staging` | `<prefix>:environment:staging` |
| `deploy-production` | `production` | `<prefix>:environment:production` |

ここで注意が要ります。**environment 形式の `sub` には ref が含まれません。** つまり
「`main` からの実行に限る」という制約が、この2ジョブについては `sub` の側から効かなく
なります。そこで手順Bで設定した environment のデプロイ可能ブランチ制限が効いてきます。
防御の分担は「`build` は `sub` の ref 条件で」「デプロイの2ジョブは environment の
ブランチ設定で」`main` に限定される、という形になります。

### 手順E: 実デプロイを観測する

修正後の実行（30565326843）で3ジョブすべてが成功しました。観測結果は次のとおりです。

| 観測項目 | 結果 |
|---|---|
| OIDC 認証 | 3ジョブとも成功。`Authenticated as assumedRoleId AROAQR5EPHW6ZPSNRRVTQ:GitHubActions` |
| ECR への push | 成功。イメージタグはコミット SHA |
| artifact | `build` で `deployment-manifest`（281 bytes）を保存 → `deploy-staging` で取得成功 |
| Lambda | 初回作成の分岐を通過（`Lambda 関数がまだ無いため初回作成します`） |
| バージョン | `publish-version` でバージョン `1` を公開、`staging` エイリアスを作成 |
| production | `staging と同じバージョンを production へ: 1` |
| 所要時間 | `build` 37秒 / `deploy-staging` 30秒 / `deploy-production` 11秒 |
| 承認待ち | `deploy-staging` 完了から `deploy-production` 開始まで**約5時間55分停止** |

デプロイした関数が実際に動くことも確認しました。`stage-07` の時点では `CMD` が参照する
モジュールが存在せず起動できなかったイメージが、ここで初めて実行されています。

```
{"month_count": 3, "total_amount": "652500", "output": {...}}
```

実行時の実測値は次のとおりです（`data/sales_sample.csv`・3か月分、512MB 割当）。

| 実行 | Duration | Init Duration | 課金対象 | Max Memory Used |
|---|---|---|---|---|
| 1回目（コールドスタート） | 754.29ms | 1601.33ms | 2356ms | 95MB |
| 2回目（ウォームスタート） | 157.04ms | — | 158ms | 95MB |

## 5. 何が変わったか

このステージ完了時点（タグ `stage-08`）の `.github/workflows/deploy.yml` を以下に転記
します。行番号引用はすべてこのブロックの行を指します。

<!-- transcript: .github/workflows/deploy.yml @ stage-08 -->
```
1| # Stage 8: 実際に AWS へデプロイする。
2| # 長期のアクセスキーは置かない。OIDC でその実行専用の一時認証を取る。
3| name: Deploy
4| 
5| on:
6|   push:
7|     branches: [main]
8|     paths-ignore:
9|       - "docs/**"
10|       - "**/*.md"
11|   workflow_dispatch:
12|     inputs:
13|       rollback_to_version:
14|         description: ロールバック先の Lambda バージョン番号（空ならロールバックしない）
15|         required: false
16|         default: ""
17|         type: string
18| 
19| concurrency:
20|   # デプロイ先（Lambda 関数1つ、staging/production エイリアス）は ref に
21|   # 依存しない。ref 別にグループを分けると、main への push によるデプロイと
22|   # 別ブランチからの workflow_dispatch（ロールバック）が同時に走り、同じ
23|   # 関数に publish-version / update-alias を競合させてしまう。だから
24|   # グループは固定の定数にし、走行中のものを消さずに待たせる。
25|   group: deploy
26|   cancel-in-progress: false
27| 
28| permissions:
29|   contents: read
30| 
31| jobs:
32|   build:
33|     name: Build & Push to ECR
34|     runs-on: ubuntu-latest
35|     timeout-minutes: 20
36|     permissions:
37|       contents: read
38|       # OIDC のトークンを発行してもらうために必要。これが無いと
39|       # aws-actions/configure-aws-credentials は認証できない
40|       # （同 action の README で明記されている必須 permission）。
41|       id-token: write
42|     steps:
43|       - name: リポジトリを取得する
44|         uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
45|         with:
46|           persist-credentials: false
47| 
48|       # 長期のアクセスキーは使わない。この実行のためだけの一時認証を取る。
49|       - name: AWS の一時認証を取得する
50|         uses: aws-actions/configure-aws-credentials@e6de054238d6b7531b4efff3b6587d9aade6a06c  # v6.2.3
51|         with:
52|           role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
53|           aws-region: ${{ vars.AWS_REGION }}
54|           # このリポジトリは public。アカウント ID がログに出るのを防ぐ
55|           # （AWS_ROLE_ARN をシークレットにしているのと同じ理由）。
56|           mask-aws-account-id: "true"
57| 
58|       - name: ECR にログインする
59|         id: ecr
60|         uses: aws-actions/amazon-ecr-login@d539f0932e70871a027e9d5a9d8fc38589180a64  # v2.1.6
61| 
62|       - name: イメージをビルドして push する
63|         env:
64|           REGISTRY: ${{ steps.ecr.outputs.registry }}
65|           REPOSITORY: ${{ vars.ECR_REPOSITORY }}
66|           IMAGE_TAG: ${{ github.sha }}
67|         run: |
68|           uri="${REGISTRY}/${REPOSITORY}:${IMAGE_TAG}"
69|           docker build --tag "${uri}" .
70|           docker push "${uri}"
71| 
72|       # Stage 0 で予告した「ジョブ間でファイルを渡す仕組み」がここで要る。
73|       #
74|       # 【マスクの限界】REGISTRY（"<ACCOUNT_ID>.dkr.ecr.<region>.amazonaws.com"）は
75|       # 上の configure-aws-credentials の mask-aws-account-id でこのジョブの
76|       # ログ上はマスクされるが、マスクが効くのはランナーのログストリームだけ。
77|       # artifact としてアップロードするファイルの中身にも、GITHUB_STEP_SUMMARY にも
78|       # マスクは一切効かない。このリポジトリは public なので、artifact に書いた
79|       # 内容は誰でもダウンロードできる。だからこのマニフェストには、アカウント ID を
80|       # 含む完全な image URI ではなく、そこに含まれない部品（リポジトリ名・
81|       # コミット SHA）だけを書く。フルの URI は deploy-staging 側で、そのジョブ
82|       # 自身が取得したアカウント ID から組み立て直す。
83|       - name: デプロイ用のマニフェストを書き出す
84|         env:
85|           ECR_REPOSITORY_NAME: ${{ vars.ECR_REPOSITORY }}
86|           COMMIT_SHA: ${{ github.sha }}
87|         run: |
88|           cat > deployment-manifest.json <<JSON
89|           {
90|             "ecr_repository": "${ECR_REPOSITORY_NAME}",
91|             "commit_sha": "${COMMIT_SHA}",
92|             "built_at": "$(date --iso-8601=seconds)"
93|           }
94|           JSON
95|           cat deployment-manifest.json
96| 
97|       - name: マニフェストを artifact として保存する
98|         uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a  # v7.0.1
99|         with:
100|           name: deployment-manifest
101|           path: deployment-manifest.json
102|           retention-days: 7
103| 
104|   deploy-staging:
105|     name: Deploy to staging
106|     runs-on: ubuntu-latest
107|     needs: build
108|     timeout-minutes: 15
109|     environment: staging
110|     permissions:
111|       contents: read
112|       # OIDC で AWS の一時認証を取るために必要。
113|       id-token: write
114|     steps:
115|       - name: マニフェストを取得する
116|         uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c  # v8.0.1
117|         with:
118|           name: deployment-manifest
119| 
120|       - name: AWS の一時認証を取得する
121|         uses: aws-actions/configure-aws-credentials@e6de054238d6b7531b4efff3b6587d9aade6a06c  # v6.2.3
122|         with:
123|           role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
124|           aws-region: ${{ vars.AWS_REGION }}
125|           mask-aws-account-id: "true"
126| 
127|       # docs/aws-bootstrap.md 3.7 節の設計どおり、Lambda 関数はここで
128|       # 初回作成する（ECR にイメージが無いと関数を作れないため、CloudShell
129|       # 側の一度きりの手作業では作れない。関数を作れるのは、イメージが
130|       # 実際に存在するこの時点だけ）。存在すれば更新、無ければ作成する。
131|       #
132|       # 実行ロールの名前 sales-report-etl-lambda-role は同手順書 3.3 節で
133|       # 固定した名前規約（学習者から受け取る4値には含まれない）。この名前と
134|       # 実行時に取得したアカウント ID から ARN を組み立てる。
135|       #
136|       # 【マスクの限界】account_id は上の configure-aws-credentials の
137|       # mask-aws-account-id により「このジョブのログ」ではマスクされる。
138|       # しかし GITHUB_STEP_SUMMARY と artifact にはマスクが効かないため、
139|       # account_id・exec_role_arn・image_uri（いずれもアカウント ID を含む）は
140|       # このステップの中だけで使い、ステップサマリにも次の artifact にも
141|       # 一切書き出さない（zizmor の finding が消えてもリスククラスは消えない、
142|       # という Stage 6 の教訓と同じ型）。
143|       #
144|       # 初回作成時の --timeout / --memory-size を明示するのは、デフォルト
145|       # （3秒/128MB）のまま作ってしまうと、2回目以降は update-function-code しか
146|       # 呼ばないため、その既定値が恒久設定として残ってしまうから。
147|       #
148|       # 初回デプロイ後に実測した値（data/sales_sample.csv・3か月分）:
149|       #   コールドスタート Duration 754.29ms + Init Duration 1601.33ms（課金 2356ms）
150|       #   ウォームスタート Duration 157.04ms / Max Memory Used 95MB（いずれも 512MB 割当）
151|       # 60秒は実測の20倍以上、512MB も実使用 95MB に対して過大である。それでも
152|       # 下げていないのは、Lambda の CPU 割当がメモリ割当に比例するため、256MB へ
153|       # 落とすと実行時間が延び、GB-秒での課金がほぼ変わらないからである。
154|       #
155|       # なお、この2つの値が効くのは create-function のときだけで、すでに存在する
156|       # 関数には反映されない（変えるなら update-function-configuration を明示的に
157|       # 呼ぶ必要がある）。
158|       - name: Lambda を作成または更新して staging エイリアスを張り替える
159|         env:
160|           FUNCTION_NAME: ${{ vars.LAMBDA_FUNCTION_NAME }}
161|           EXEC_ROLE_NAME: sales-report-etl-lambda-role
162|           CREATE_TIMEOUT_SECONDS: "60"
163|           CREATE_MEMORY_SIZE_MB: "512"
164|           # 上の configure-aws-credentials も output-env-credentials（既定 true）で
165|           # 同じ値を環境変数として渡してくるが、ここで vars.AWS_REGION から
166|           # 明示的に渡し直す（この run: の中で参照する変数は env: 経由にする
167|           # という規約に合わせるため）。
168|           AWS_REGION: ${{ vars.AWS_REGION }}
169|         run: |
170|           ecr_repository=$(python -c "import json;print(json.load(open('deployment-manifest.json'))['ecr_repository'])")
171|           image_tag=$(python -c "import json;print(json.load(open('deployment-manifest.json'))['commit_sha'])")
172| 
173|           # account_id はマニフェストに書かず、ここで取得したものだけを使う。
174|           account_id=$(aws sts get-caller-identity --query Account --output text)
175|           image_uri="${account_id}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ecr_repository}:${image_tag}"
176|           echo "デプロイするイメージのタグ: ${image_tag}"
177| 
178|           if aws lambda get-function --function-name "${FUNCTION_NAME}" >/dev/null 2>&1; then
179|             echo "既存の Lambda 関数を更新します"
180|             aws lambda update-function-code \
181|               --function-name "${FUNCTION_NAME}" \
182|               --image-uri "${image_uri}" >/dev/null
183|             aws lambda wait function-updated --function-name "${FUNCTION_NAME}"
184|           else
185|             echo "Lambda 関数がまだ無いため初回作成します（docs/aws-bootstrap.md 3.7 節）"
186|             exec_role_arn="arn:aws:iam::${account_id}:role/${EXEC_ROLE_NAME}"
187|             aws lambda create-function \
188|               --function-name "${FUNCTION_NAME}" \
189|               --package-type Image \
190|               --code ImageUri="${image_uri}" \
191|               --role "${exec_role_arn}" \
192|               --timeout "${CREATE_TIMEOUT_SECONDS}" \
193|               --memory-size "${CREATE_MEMORY_SIZE_MB}" >/dev/null
194|             aws lambda wait function-active --function-name "${FUNCTION_NAME}"
195|           fi
196| 
197|           version=$(aws lambda publish-version --function-name "${FUNCTION_NAME}" --query Version --output text)
198|           echo "公開したバージョン: ${version}"
199|           aws lambda update-alias --function-name "${FUNCTION_NAME}" \
200|             --name staging --function-version "${version}" \
201|             || aws lambda create-alias --function-name "${FUNCTION_NAME}" \
202|                  --name staging --function-version "${version}"
203|           {
204|             echo "## staging へデプロイしました"
205|             echo ""
206|             echo "- ECR リポジトリ: \`${ecr_repository}\`"
207|             echo "- イメージタグ（commit sha）: \`${image_tag}\`"
208|             echo "- Lambda バージョン: ${version}"
209|           } >> "${GITHUB_STEP_SUMMARY}"
210| 
211|   deploy-production:
212|     name: Deploy to production
213|     runs-on: ubuntu-latest
214|     needs: deploy-staging
215|     timeout-minutes: 15
216|     # この environment には承認者が設定してある。ここでワークフローが止まり、
217|     # 人が承認するまで先へ進まない。
218|     environment: production
219|     permissions:
220|       contents: read
221|       # OIDC で AWS の一時認証を取るために必要。
222|       id-token: write
223|     steps:
224|       - name: AWS の一時認証を取得する
225|         uses: aws-actions/configure-aws-credentials@e6de054238d6b7531b4efff3b6587d9aade6a06c  # v6.2.3
226|         with:
227|           role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
228|           aws-region: ${{ vars.AWS_REGION }}
229|           mask-aws-account-id: "true"
230| 
231|       - name: production エイリアスを張り替える
232|         env:
233|           FUNCTION_NAME: ${{ vars.LAMBDA_FUNCTION_NAME }}
234|           ROLLBACK_TO: ${{ inputs.rollback_to_version }}
235|         run: |
236|           if [ -n "${ROLLBACK_TO}" ]; then
237|             target="${ROLLBACK_TO}"
238|             echo "ロールバック先として指定されたバージョン: ${target}"
239|           else
240|             target=$(aws lambda get-alias --function-name "${FUNCTION_NAME}" \
241|               --name staging --query FunctionVersion --output text)
242|             echo "staging と同じバージョンを production へ: ${target}"
243|           fi
244|           aws lambda update-alias --function-name "${FUNCTION_NAME}" \
245|             --name production --function-version "${target}" \
246|             || aws lambda create-alias --function-name "${FUNCTION_NAME}" \
247|                  --name production --function-version "${target}"
248|           {
249|             echo "## production を更新しました"
250|             echo ""
251|             echo "- Lambda バージョン: ${target}"
252|           } >> "${GITHUB_STEP_SUMMARY}"
```

### OIDC の仕組みと `id-token: write`

`deploy.yml` の36〜41行目で、`build` ジョブにだけ `id-token: write` を付けています。これは
「GitHub Actions の OIDC プロバイダに、この実行を証明するトークンを発行させてよい」という
許可です。この permission があると、ランナーの環境に `ACTIONS_ID_TOKEN_REQUEST_URL` と
`ACTIONS_ID_TOKEN_REQUEST_TOKEN` が入り、`aws-actions/configure-aws-credentials`
（`deploy.yml` の50行目）がそこからトークンを取得して AWS の STS に渡します。

`deploy.yml` でこれをトップレベルではなくジョブ単位で付けているのは、Stage 6 の原則
（必要なジョブに必要な分だけ）に従ったためです。28〜29行目のトップレベルは
`contents: read` のままで、3つのジョブがそれぞれ自分に必要な `id-token: write` を足して
います。

トークンの中身のうち、AWS 側の検証で最も重要なのが `sub`（subject）クレームです。これが
「どのリポジトリの、どのブランチ／環境の実行か」を表します。手順Dで見たとおり、
`environment:` の有無でこの値の形が変わります。信頼ポリシーの `sub` 条件を
`repo:<owner>/<repo>:*` のように広げると、そのリポジトリのあらゆる実行からロールを
引き受けられるようになるので、狭く書くことがこのロールの安全性そのものになります。
詳しくは [docs/aws-bootstrap.md](../aws-bootstrap.md) の 3.2 節を参照してください。

### artifact によるジョブ間の受け渡し（Stage 0 の伏線の回収）

Stage 0 で「ジョブ間でファイルを渡す仕組みは後で扱う」と予告した `artifact` を、ここで
実際に使っています。`deploy.yml` の97〜102行目で `upload-artifact` により
`deployment-manifest` という名前で保存し、115〜118行目の `download-artifact` で
`deploy-staging` 側が受け取ります。ジョブは別のランナー（別のマシン）で動くため、
ファイルはこの仕組みを通さない限り引き継がれません。

値が1つなら、ジョブの `outputs` でも渡せます。それでもファイルの形にしたのは、デプロイの
記録は「何を・いつ・どのコミットから作ったか」と増えていくものだからです。実測では
281 bytes の JSON が7日間（`deploy.yml` の102行目の `retention-days: 7`）保持される形に
なりました。

**この artifact には意図的にアカウント ID を書いていません。** `deploy.yml` の72〜82行目の
コメントに書いたとおり、`mask-aws-account-id` によるマスクが効くのはランナーのログ
ストリームだけで、artifact の中身にも `GITHUB_STEP_SUMMARY` にも効きません。public
リポジトリの artifact は誰でもダウンロードできるので、完全な image URI ではなく、
アカウント ID を含まない部品（ECR リポジトリ名とコミット SHA）だけを渡し、
`deploy-staging` 側が175行目で自分の取得したアカウント ID から URI を組み立て直しています。

### environment と承認フロー

`deploy.yml` の109行目と218行目の `environment:` が、そのジョブを environment に結び付けて
います。`production` 側にだけ承認者を設定してあるため、216〜217行目のコメントのとおり、
ワークフローはここで停止します。

実測では、`deploy-staging` が完了してから `deploy-production` が始まるまで**約5時間55分**
かかりました。この間、実行の状態は `waiting` で、失敗ではありません。承認するまで
何も起きず、承認した瞬間に11秒で完了しています。

environment にはもう1つの役割があります。手順Dで説明したとおり、environment 形式の `sub`
には ref が含まれないため、**ブランチの限定は environment 側のデプロイ可能ブランチ設定が
担っています。** environment を「承認を挟むための仕組み」としてだけ理解していると、この
点を見落とします。

### エイリアスによるロールバック

Lambda の**バージョンは不変**です。`deploy.yml` の197行目の `publish-version` は、その時点の
コードと設定を固定した番号付きのスナップショットを作ります。一度公開したバージョン 1 の
中身は、あとから何をしても変わりません。

変わるのは**エイリアス**の向き先だけです。`deploy.yml` の199〜202行目で `staging` エイリアスを
新しいバージョンへ張り替え、244〜247行目で `production` エイリアスを張り替えています。つまり
デプロイとは「エイリアスの向き先を変えること」であり、ロールバックとは「向き先を前の
番号へ戻すこと」です。新しいイメージのビルドも push も要りません。

戻す先を指定する経路が、`deploy.yml` の11〜17行目の `workflow_dispatch` の入力
`rollback_to_version` です。236〜243行目で、この入力が空でなければその番号へ、空なら `staging` と同じ番号へ
`production` を向けます。**ロールバックの手段を最初のデプロイと同時に用意しているのが
ここでの要点です。**

### `concurrency` に `cancel-in-progress: false` を選んだ理由

`deploy.yml` の19〜26行目です。Stage 3 以降の `CI` ワークフローでは
`cancel-in-progress: ${{ github.event_name == 'pull_request' }}` として、新しい push が来たら
走行中の検査を打ち切っていました。**検査は途中で止めても失われるものがありませんが、
デプロイは違います。** `update-function-code` と `publish-version` と `update-alias` の
途中で打ち切られると、どの状態まで進んだのかが分からなくなります。だから走行中のものは
消さずに待たせます。

グループ名を `deploy.yml` の20〜25行目のコメントのとおり `ref` を含まない固定値 `deploy` にしているのも
同じ理由です。デプロイ先の Lambda 関数は1つしかないので、`main` への push によるデプロイと
別ブランチからの `workflow_dispatch`（ロールバック）が同時に走ると、同じ関数に対する操作が
競合します。

### なぜロール ARN だけシークレットなのか

`deploy.yml` の52行目は `${{ secrets.AWS_ROLE_ARN }}`、53行目は `${{ vars.AWS_REGION }}` と、
参照の仕方が違います。ARN には AWS アカウント ID が含まれ、このリポジトリは public です。
シークレットにすればログで自動的にマスクされます。54〜56行目の `mask-aws-account-id: "true"`
は、ARN 以外の経路（ECR のレジストリ URI など）に現れるアカウント ID もマスクさせるための
指定です。

ただし**マスクはログにしか効きません。** artifact とステップサマリには効かない、という
限界を前提に書いたのが、前述の `deployment-manifest` の設計です。

## 6. つまずきポイント

- **`id-token: write` を忘れると、AWS に到達する前に失敗する** — 実測した文言は次のとおり
  です。この失敗は GitHub 側でトークンを要求する段階で起きるため、AWS の信頼ポリシーが
  正しいかどうかとは無関係です。

  ```
  It looks like you might be trying to authenticate with OIDC.
  Did you mean to set the `id-token` permission?
  ...
  ##[error]Credentials could not be loaded, please check your action inputs:
  Could not load credentials from any providers
  ```

  action が親切にも `id-token` permission を疑うヒントを出してくれます。ただし、この
  メッセージが出るまでに**12回のリトライで約80秒**かかるので、ログの末尾だけを見て
  「ネットワークの問題か」と誤解しないでください。

- **信頼ポリシーの `sub` が合っていないと、エラーの文言が全く別になる** — こちらは
  AWS 側の拒否です。

  ```
  Could not assume role with OIDC: Not authorized to perform sts:AssumeRoleWithWebIdentity
  ```

  上の `id-token` 欠落のエラーと混同しないでください。**「AWS まで到達したが断られた」のか
  「AWS に到達すらしていない」のかで、直すべき場所が GitHub 側と AWS 側に分かれます。**

- **`environment:` を足すと `sub` の形が変わる** — 手順Dで踏んだ問題です。environment を
  後から追加すると、それまで通っていた信頼ポリシーが**そのジョブに対してだけ**効かなく
  なります。`build` が成功して `deploy-staging` だけが落ちる、という非対称な失敗の仕方が
  手がかりになります。

- **environment の承認待ちは失敗ではない** — 実行のステータスは `waiting` で、
  `gh run view` では `Deploy to production=waiting` と表示されます。放置すると期限切れに
  なります。CI が赤くなっていないか確認するつもりで見ると、いつまでも「実行中」に見えて
  混乱するので、承認待ちであることを認識してください。

- **`--timeout` と `--memory-size` は初回作成のときにしか効かない** — `deploy.yml` の
  178〜195行目のとおり、2回目以降は `update-function-code` しか呼びません。つまり
  162〜163行目の値を後から変えても、**すでに存在する関数の設定は変わりません。** 変える
  なら `update-function-configuration` を明示的に呼ぶ必要があります。既定値
  （3秒/128MB）のまま関数を作ってしまうと、その既定値が恒久設定として残ります。

- **`workflow_dispatch` の入力は `push` で起動したときには空になる** — `deploy.yml` の
  234行目の `${{ inputs.rollback_to_version }}` は、`push` トリガーでは空文字列に
  なります。236行目の `if [ -n "${ROLLBACK_TO}" ]` はこれを前提にした分岐です。

## 7. 演習課題

以下の3問は [docs/stages/answers/stage-08.md](answers/stage-08.md) に解答があります。
まず自分で予想してから答えを見てください。

1. **問1**: `build` ジョブから `id-token: write` を外すと何が起きるか。実際に試して失敗
   メッセージを記録する。**このとき、`main` を汚さずに実験する方法も併せて考えること。**
2. **問2**: `workflow_dispatch` で `rollback_to_version` に1つ前のバージョンを指定して
   実行し、`production` エイリアスが戻ることを確認する。ロールバックは「試したことがある
   人」しか本番でできない。
3. **問3**: `deploy-production` から `environment: production` を消すと何が起きるか予想し、
   **実行はせずに**説明する。承認なしで本番が更新されてしまうため実演しない。

## 8. 実務への持ち込みメモ

ロールは環境ごとに分けてください。この教材では学習の単純さを優先して1つのロールを3つの
ジョブで共用していますが、実務では `staging` 用と `production` 用を別のロールにし、
それぞれの信頼ポリシーで対応する environment の `sub` だけを許可します。そうすれば
`staging` のデプロイ経路が乗っ取られても `production` には手が届きません。

信頼ポリシーの `sub` は可能な限り狭く書き、**広げたくなったら、まず「なぜ今の条件で
足りないのか」を突き止めてください。** 今回のように、条件を広げる（`*` にする）ことでも
問題は消えますが、それは原因を消したのではなく検知を消しただけです。実際の原因は
「environment を足したことで `sub` の形が変わった」という具体的な事実でした。

ロールバックの手段は、最初のデプロイと同時に用意してください。「戻す方法は後で考える」と
した場合、それを考えることになるのは決まって障害の最中です。そして**用意しただけでは
足りません。** 一度も実行したことのない手順は、本番で初めて動かすことになります。演習の
問2 を必ず実施してください。

---

## 補遺: ECS Fargate を選ぶ場合の差分

この教材では Lambda（コンテナイメージ）を選びましたが、同じイメージを ECS Fargate へ
デプロイする選択肢もあります。**この補遺は実装・実測を伴わない整理**です。実際に選ぶ際は
AWS の公式ドキュメント（Amazon ECS デベロッパーガイド、AWS Lambda デベロッパーガイド）で
現在の仕様を確認してください。

### ワークフローのどこが変わるか

`build` ジョブ（ECR への push）はほぼそのまま使えます。イメージの置き場所は同じ ECR
だからです。変わるのはデプロイのジョブで、`update-function-code` → `publish-version` →
`update-alias` という流れが、おおむね次の流れに置き換わります。

1. 現行のタスク定義を取得し、イメージ URI を差し替えた新しいリビジョンを登録する
2. サービスの `task-definition` を新しいリビジョンに更新する
3. デプロイが安定するまで待つ（`aws ecs wait services-stable` に相当する待機）

`aws-actions/amazon-ecs-render-task-definition` と `aws-actions/amazon-ecs-deploy-task-definition`
という公式 action が用意されており、1と2はそれを使うのが一般的です。

### 追加で必要になる AWS 資源

Lambda では関数と実行ロールだけで動きましたが、ECS では VPC・サブネット・セキュリティ
グループ・ECS クラスタ・タスク定義・サービスが必要になります。外部から HTTP で受ける
なら ALB も加わります。ブートストラップ手順書に相当する準備の分量が、目に見えて増えます。

### コストモデルの違い

Lambda は**リクエストの実行時間に対して課金**され、呼ばれていない間はゼロです。今回の
実測（ウォームスタート 158ms・512MB）のような処理なら、月に数千回呼んでも無料利用枠の
範囲に収まる規模です。Fargate は**タスクが動いている間ずっと課金**されます。待機時間にも
料金がかかるかわりに、起動のたびの初期化（今回の実測で 1601.33ms）が無く、実行時間の
上限もありません。

### どちらを選ぶか

起動が散発的で1回が短時間なら Lambda が向きます。今回の ETL はこの形です。常時稼働が
必要、処理が長時間にわたる、あるいは **Lambda の実行時間上限（15分）に収まらない**なら
Fargate を検討します。イメージのサイズが大きくコールドスタートが問題になる場合も
Fargate 側の理由になります。

### ロールバックの考え方の違い

Lambda ではエイリアスの向き先を前のバージョン番号に戻します。ECS ではタスク定義の
リビジョンを前のものに戻してサービスを更新します。**「不変のスナップショットに番号が
振られ、どれを使うかを指す仕組みが別にある」という構造は同じ**です。この構造さえ
つかんでいれば、どちらのサービスでもロールバックの設計は同じ考え方で組めます。
