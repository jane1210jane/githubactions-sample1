# AWS ブートストラップ手順書

Stage 8 では、GitHub Actions のワークフローが実際に AWS へコンテナイメージを push し、
Lambda 関数をデプロイします。その前に、AWS 側に「入口」を一度だけ手作業で用意する必要が
あります。この文書はその手順です。

## 1. なぜ手作業なのか

GitHub Actions が AWS に入る方法は OIDC（OpenID Connect）です。ワークフロー実行のたびに
GitHub が短命な署名付きトークンを発行し、AWS 側がそれを検証して IAM ロールを一時的に貸します。
長期のアクセスキーをどこにも保存しないので、鍵が漏れるリスクそのものがありません。

ただし、この仕組みが機能するには、AWS 側に「このロールは GitHub Actions からの
このトークンを信頼する」という IAM ロール（と、そのロールを名乗るための OIDC プロバイダ登録）が
**先に存在していなければなりません**。ロールが無ければワークフローは何も引き受けられず、
ロールを作るには「IAM ロールを作れる権限」を持った認証情報が要ります。

その認証情報を CI に置いてしまうと、「CI に強い権限を持たせないために OIDC を使う」という
そもそもの目的が崩れます。CI に置ける認証情報は、CI 自身が使う範囲に限定された弱い権限で
なければ意味がありません。だから、最初の「入口」を作る一度きりの作業だけは、人間が
自分の認証情報で行います。実務でも理由は同じで、最初のロール作成は手作業か、
IAM 管理権限を持つ別の基盤チームが行うのが一般的です。

## 2. 前提

- AWS アカウントを持っていること。
- リージョンは **`ap-northeast-1`**（東京）に統一します。以下のコマンドはすべてこの前提で書いています。
- ブラウザから AWS マネジメントコンソールにログインできること。**AWS CloudShell**
  （コンソール右上のアイコンから起動できるブラウザ内ターミナル）を使うので、
  ローカルに AWS CLI をインストールする必要はありません。
- **CloudShell に Docker は入っていません。** そのため、この手順書には
  「イメージをビルドして push する」手順は含めません（3.7 節で理由を詳しく書きます）。
  Docker が必要な作業は Stage 7・Stage 8 で GitHub Actions のランナー上で行われます。

**費用について**: IAM ロール・OIDC プロバイダの作成・保持自体は無料です。S3・Lambda は
このカリキュラムで扱う程度のデータ量・呼び出し回数であれば無料利用枠の範囲に収まります。
唯一、**Amazon ECR のイメージストレージだけは無料利用枠を超えると少額課金されます**
（本書執筆時点の AWS 公式料金ページで、ECR プライベートリポジトリのストレージは
$0.10/GB/月、新規アカウントは最初の12か月間 500MB/月まで無料）。学習用の小さな
コンテナイメージを数世代分保持しても、月あたり数十円〜百円程度に収まる規模です。
気になる場合は、6章の後片付け手順でリポジトリごと削除してください。

## 3. 手順

すべて **AWS CloudShell**（リージョンを `ap-northeast-1` に切り替えた状態）で実行します。
CloudShell はセッションを閉じると変数がリセットされるので、途中で閉じてしまった場合は
3.0 節からやり直してください（すでに作成済みのリソースは、同じ名前で再作成しようとすると
エラーになるので安全に気づけます）。

### 3.0 共通の変数を設定する

以降のすべてのコマンドで使う値を、最初にまとめて設定します。

```bash
export OWNER=jane1210jane
export REPO=githubactions-sample1
export REGION=ap-northeast-1
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export DEPLOY_ROLE_NAME=github-actions-sales-report
export EXEC_ROLE_NAME=sales-report-etl-lambda-role
export ECR_REPO_NAME=sales-report
export BUCKET_NAME=sales-report-etl-${ACCOUNT_ID}
export FUNCTION_NAME=sales-report-etl
export OIDC_PROVIDER_ARN="arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"

echo "ACCOUNT_ID=$ACCOUNT_ID"
```

`ACCOUNT_ID` が空や `None` になっていたら、CloudShell がまだ認証情報を取得できていません。
少し待つか、CloudShell を再起動してください。

**注意**: `OWNER`/`REPO` だけでは、後で使う `sub`（3.2 節）を組み立てられません。
GitHub が発行する `sub` クレームには、リポジトリ名だけでなく数値の ID が入る場合があり、
その ID は `OWNER`/`REPO` の文字列からは導出できないためです。3.2 節で別途確認します。

### 3.1 GitHub の OIDC プロバイダを登録する

AWS アカウントに「`token.actions.githubusercontent.com` を発行元として信頼する」ことを
一度だけ登録します。**AWS アカウントに1つあれば足り、複数のリポジトリで共用できます。**
すでに他のプロジェクトで登録済みなら、この手順は不要です。次のコマンドで確認できます。

```bash
aws iam list-open-id-connect-providers \
  --query "OpenIDConnectProviderList[].Arn" --output text \
  | grep -q token.actions.githubusercontent.com \
  && echo "already registered — skip" \
  || aws iam create-open-id-connect-provider \
       --url https://token.actions.githubusercontent.com \
       --client-id-list sts.amazonaws.com
```

`--thumbprint-list` を渡していませんが、これは省略が正しい書き方です。以前は GitHub の
TLS証明書のサムプリントを手で渡す必要がありましたが、現在の IAM はプロバイダのサーバー証明書から
上位 CA のサムプリントを自動取得するため、渡しても無視されます。

この ARN は 3.0 節ですでに `OIDC_PROVIDER_ARN` として組み立ててあります（アカウント ID から
機械的に決まる値なので、実際に作成する前でも組み立てられます）。

```bash
echo "$OIDC_PROVIDER_ARN"
```

### 3.2 デプロイ用ロールを作る（信頼ポリシーが要点）

GitHub Actions のワークフローが `sts:AssumeRoleWithWebIdentity` で引き受けるロールです。
**信頼ポリシーの `Condition` にある `sub`（subject）の値が、このロールの安全性そのもの**
なので、じっくり読んでください。

`sub` の正しい値を決めるために、まずこのリポジトリの OIDC subject claim の実際の形を
確認します（なぜこの確認が要るかは、次の見出し「なぜ `sub` をこの値にするか」で
説明します）。**GitHub CLI が使える環境**（CloudShell である必要はありません。手元の
PC や Codespaces でも構いません）で次を実行してください。

```bash
gh api repos/jane1210jane/githubactions-sample1/actions/oidc/customization/sub --jq .sub_claim_prefix
```

本書作成時点（2026-07-29）でこのコマンドを実行すると、次の値が返ります。

```
repo:jane1210jane@84302077/githubactions-sample1@1312756463
```

**この値は自分でも必ず再確認してください。** 以降は CloudShell 側の作業です。上のコマンドの
出力を `SUB_CLAIM_PREFIX` に設定し、`main` ブランチへの参照を付け足した `SUB_CLAIM` を作ります。

```bash
export SUB_CLAIM_PREFIX="repo:jane1210jane@84302077/githubactions-sample1@1312756463"  # 上のコマンドの出力に置き換える
export SUB_CLAIM="${SUB_CLAIM_PREFIX}:ref:refs/heads/main"
echo "$SUB_CLAIM"

cat > trust-policy.json <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Federated": "${OIDC_PROVIDER_ARN}" },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "${SUB_CLAIM}"
        }
      }
    }
  ]
}
JSON

aws iam create-role \
  --role-name "$DEPLOY_ROLE_NAME" \
  --assume-role-policy-document file://trust-policy.json

export DEPLOY_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${DEPLOY_ROLE_NAME}"
echo "$DEPLOY_ROLE_ARN"
```

#### なぜ `sub` をこの値にするか

GitHub が発行する OIDC トークンの `sub` クレームは、ワークフローが**何によって・どの ref に対して**
起動されたかを表す文字列です。代表的な形は次のとおりです（`<prefix>` は
`repo:<OWNER>@<owner id>/<REPO>@<repo id>` の部分を指します。この ID 入りの形になる理由は
このあとの「immutable subject claim について」で説明します）。

| トリガー | `sub` の形 |
|---|---|
| `push`（ブランチへの push） | `<prefix>:ref:refs/heads/<branch>` |
| `pull_request` | `<prefix>:pull_request` |
| `workflow_dispatch`（手動実行） | `<prefix>:ref:refs/heads/<dispatch した ref>` |
| ジョブが `environment:` を指定している場合 | どのトリガーでも `<prefix>:environment:<環境名>` |

Stage 8 のデプロイワークフロー（Task 10 で追加）は `main` への `push` と、ロールバック用の
`workflow_dispatch` の2つで起動します。`workflow_dispatch` は「その時点でワークフロー定義が
存在するブランチ」から実行するのが通常で、マージ後は `main` 以外から実行する意味がありません。
つまり実際に起動される2パターンはどちらも ref が `refs/heads/main` になるため、
**`${SUB_CLAIM_PREFIX}:ref:refs/heads/main` という1つの条件でこの2つのトリガーを
どちらもカバーできます**。`environment:` は使わない設計なので、その形は考慮していません。

これを `${SUB_CLAIM_PREFIX}:*` のように緩めると、**このリポジトリの任意のブランチ・
任意の PR からロールを引き受けられてしまいます。** 特に `pull_request` を含めてしまうと
危険です。**`pull_request` でトリガーされたワークフローは、fork から送られた PR であっても、
その fork のコードを実際にチェックアウトして実行します**（「fork のコードは動かない」という
思い込みは誤りです）。それでも致命的にならないのは、GitHub 側が別の防御として、
fork からの `pull_request` トリガーには読み取り専用の `GITHUB_TOKEN` しか渡さず、
リポジトリのシークレットも、OIDC の `id-token`（このロールを引き受けるために必要なトークン）も
渡さないためです。つまり今回の危険は「fork のコードが動くこと」自体ではなく、「`sub` の条件を
広げて GitHub 側のこの防御に頼り切ってしまうこと」にあります。trust policy 側でも
`ref:refs/heads/main` に絞ることで、二重の防御にしています。（余談: `pull_request_target` は
これとは逆に、ベースブランチ側のワークフロー定義がシークレット付きで動く一方、既定では
ベースブランチのコードしかチェックアウトしません。もし `pull_request_target` のワークフローが
誤って fork 側のコードをチェックアウトして実行するステップを含んでいたら、そのコードが
シークレットにアクセスできてしまう、という別の危険があります。今回の `deploy.yml` は
`pull_request_target` を使わないので、この危険自体は関係ありません。）

上記の1条件で、`push` と `workflow_dispatch` の両方を過不足なくカバーできます。

#### immutable subject claim について（この手順書の `sub` が ID 入りである理由）

GitHub は2026年に、`sub` クレームにリポジトリ・オーナーの数値 ID を焼き込む
「immutable subject claim」という形式を導入しました。**2026-07-15 以降に作成された
リポジトリは、自動的にこの ID 入りの形式でトークンを発行します。** 名前は変更・再利用が
起こり得ますが、数値 ID は変わらないため、リポジトリ名やオーナー名を再利用した第三者が
古い信頼ポリシーを乗っ取れないようにする、というのがこの変更の狙いです。

このリポジトリの `created_at` は `2026-07-26T11:49:43Z` で、カットオフより後に作成されています。
そのため `sub` は自動的に ID 入りの形式になり、`repo:jane1210jane/githubactions-sample1:ref:...`
という ID なしの旧形式では**永久に一致しません**。信頼ポリシーの `sub` を旧形式のまま書くと、
GitHub Actions は正しいトークンを送っているのに AWS 側が一致と判定できず、
`AssumeRoleWithWebIdentity` が常に拒否される、という分かりにくい失敗になります。

**確認には `sub_claim_prefix` フィールドを使ってください。** `gh api
repos/<OWNER>/<REPO>/actions/oidc/customization/sub` の応答には `use_default` /
`use_immutable_subject` / `sub_claim_prefix` の3つのフィールドがありますが、
**`use_immutable_subject` は「2026-07-15 より前に作られたリポジトリが、免除を明示的に
オプトインしたかどうか」を表す切り替えフラグであり、カットオフ後に自動適用されている
かどうかを表すものではありません。** 実際にこのリポジトリで確認すると、

```
{"use_default":true,"use_immutable_subject":false,"sub_claim_prefix":"repo:jane1210jane@84302077/githubactions-sample1@1312756463"}
```

のように `use_immutable_subject` は `false` のままですが、`sub_claim_prefix` には
ID 入りの値が入っています。**`sub_claim_prefix` は経路によらず、現在実際に発行される
`sub` の接頭辞を表す権威的な値です。** `use_immutable_subject` の値だけを見て
「`false` だから旧形式のはず」と判断すると、このリポジトリのように誤ります
（本書の以前の版はこの誤りをしていました）。

**信頼ポリシーを作る直前に、自分でも `sub_claim_prefix` を再確認してください。** リポジトリの
設定や GitHub 側の挙動が将来変わる可能性があるためです。3.2 節冒頭のコマンドで再取得した値が
上と異なっていたら、その値を使ってください。

### 3.3 Lambda の実行ロールを作る

デプロイ用ロールとは別物です。デプロイ用ロールは GitHub Actions がイメージを push したり
Lambda を更新したりするために引き受けるロールですが、こちらは **Lambda 関数自身が実行中に
使うロール**です。信頼する相手も `lambda.amazonaws.com` というサービスであり、
GitHub とは無関係です。

```bash
cat > lambda-trust-policy.json <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "lambda.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
JSON

aws iam create-role \
  --role-name "$EXEC_ROLE_NAME" \
  --assume-role-policy-document file://lambda-trust-policy.json

export EXEC_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${EXEC_ROLE_NAME}"
echo "$EXEC_ROLE_ARN"
```

CloudWatch Logs へ書き込むための AWS 管理ポリシーを付けます（Lambda がログを出すために
ほぼ必須です）。

```bash
aws iam attach-role-policy \
  --role-name "$EXEC_ROLE_NAME" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
```

さらに、ETL が入出力に使う S3 バケット（3.5 で作成）への読み書き権限を、そのバケットだけに
絞ったインラインポリシーとして付けます。

```bash
cat > lambda-s3-policy.json <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SalesReportBucketReadWrite",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::${BUCKET_NAME}/*"
    },
    {
      "Sid": "SalesReportBucketList",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::${BUCKET_NAME}"
    }
  ]
}
JSON

aws iam put-role-policy \
  --role-name "$EXEC_ROLE_NAME" \
  --policy-name sales-report-etl-s3-access \
  --policy-document file://lambda-s3-policy.json
```

### 3.4 ECR リポジトリを作る

デプロイワークフローが push するコンテナイメージの置き場所です。

```bash
aws ecr create-repository \
  --repository-name "$ECR_REPO_NAME" \
  --image-scanning-configuration scanOnPush=true \
  --region "$REGION"

export ECR_REPO_ARN="arn:aws:ecr:${REGION}:${ACCOUNT_ID}:repository/${ECR_REPO_NAME}"
echo "$ECR_REPO_ARN"
```

`--region` を明示しているのは、CloudShell の既定リージョンが `ap-northeast-1` から
ずれていた場合に、実際に作られるリポジトリのリージョンと、あとで組み立てる
`ECR_REPO_ARN`（`$REGION` から機械的に組み立てた値）が食い違うのを防ぐためです。
ずれると「存在しない ARN を指す IAM ポリシー」ができてしまい、原因が分かりにくい
権限エラーになります。

### 3.5 入出力用の S3 バケットを作る

S3 バケット名は**グローバルに一意**（世界中の AWS アカウントを通じて重複不可）である
必要があるため、アカウント ID を含めた `sales-report-etl-<ACCOUNT_ID>` を使います。

```bash
aws s3api create-bucket \
  --bucket "$BUCKET_NAME" \
  --region "$REGION" \
  --create-bucket-configuration LocationConstraint="$REGION"

echo "$BUCKET_NAME"
```

`ap-northeast-1` のように `us-east-1` 以外のリージョンでは `--create-bucket-configuration`
での `LocationConstraint` 指定が必須です（省略すると `us-east-1` に作られようとして
エラーになります）。

### 3.6 デプロイ用ロールに権限を付ける

ここがこの手順書でいちばん大事な部分です。**GitHub Actions に貸すロールの権限は、
実際に必要な操作だけに絞ります。** 「動けばいい」で `"Resource": "*"` を並べたくなる
気持ちはよく分かりますが、それは「このロールが乗っ取られたときに何が起きるか」を
決める設定でもあります。

#### 狭い版（実際に付けるもの）

```bash
cat > deploy-role-policy.json <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EcrAuth",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "EcrPushAndImageRetrievalSetup",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:PutImage",
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer",
        "ecr:GetRepositoryPolicy",
        "ecr:SetRepositoryPolicy"
      ],
      "Resource": "${ECR_REPO_ARN}"
    },
    {
      "Sid": "LambdaDeploySalesReportEtl",
      "Effect": "Allow",
      "Action": [
        "lambda:GetFunction",
        "lambda:GetFunctionConfiguration",
        "lambda:CreateFunction",
        "lambda:UpdateFunctionCode",
        "lambda:PublishVersion",
        "lambda:GetAlias",
        "lambda:CreateAlias",
        "lambda:UpdateAlias"
      ],
      "Resource": [
        "arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${FUNCTION_NAME}",
        "arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${FUNCTION_NAME}:*"
      ]
    },
    {
      "Sid": "PassExecutionRoleToLambda",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "${EXEC_ROLE_ARN}"
    }
  ]
}
JSON

aws iam put-role-policy \
  --role-name "$DEPLOY_ROLE_NAME" \
  --policy-name sales-report-deploy-permissions \
  --policy-document file://deploy-role-policy.json
```

**`ecr:GetAuthorizationToken` だけ `Resource: "*"` になっている理由**: この API は
「このアカウントの ECR にログインするための認証トークンを1枚発行する」という
レジストリ全体（アカウント単位）に対する操作で、特定のリポジトリに紐付いた操作では
ありません。AWS の IAM はこの API に対してリソースレベルのアクセス許可（ARN で絞る機能）を
提供していないため、`Resource` は常に `"*"` にせざるを得ません。これは「絞り忘れ」ではなく、
この API の仕様上の制約です。一方、`ecr:PutImage` などレイヤー・イメージを実際に
読み書きする操作は特定のリポジトリの ARN に紐付いた操作なので、`sales-report` リポジトリの
ARN だけに絞れます。「絞れるものは絞り、絞れないものは絞れない理由を説明できる」状態が
最小権限です。

**`EcrPushAndImageRetrievalSetup` に push 用の5アクションだけでなく `BatchGetImage` /
`GetDownloadUrlForLayer` / `GetRepositoryPolicy` / `SetRepositoryPolicy` も入っている理由**は
3.7 節で説明します（コンテナイメージの Lambda 関数を新規作成するときに必要になる、
push とは別の操作です）。これらもすべて `sales-report` リポジトリの ARN だけに絞れます。

Lambda 側は `sales-report-etl` という関数の ARN（無修飾の ARN と、バージョン・エイリアスを
含む修飾 ARN の両方）に絞っています。`lambda:GetFunctionConfiguration` は
`lambda:GetFunction` とは別の API 権限で、Task 10 のデプロイワークフローが
`aws lambda wait function-updated` でコード更新の完了を待つ際に内部で使います
（`update-function-code` の直後に待たずに `publish-version` すると
`ResourceConflictException` になるため、この待ち合わせが必要です）。`iam:PassRole` は
Lambda の実行ロール（`sales-report-etl-lambda-role`）1つだけに絞っています。
`iam:PassRole` を `Resource: "*"` にすると、このロールを乗っ取った攻撃者は
**アカウント内の任意のロール**（管理者ロールを含む）を Lambda に渡して起動でき、
権限昇格の踏み台になります。1つのロールに絞ることで、この経路を塞いでいます。

#### 広すぎる版（比較のために書くだけで、実際には使わない）

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["ecr:*", "lambda:*", "iam:PassRole"],
      "Resource": "*"
    }
  ]
}
```

これでも「動く」ことは動きます。しかし `ecr:*` は対象リポジトリの削除やリポジトリポリシーの
書き換えまで許してしまい、`lambda:*` は無関係の Lambda 関数の削除・設定変更・
（`lambda:AddPermission` による）公開範囲の変更まで許してしまいます。`iam:PassRole` を
`Resource: "*"` にする危険性は上で説明したとおりです。「このロールの認証情報が
外部に漏れたら、攻撃者は何をできるか」を自分で問い直すと、狭い版との差が分かります。

### 3.7 なぜ Lambda 関数はここで作らないか

ここまでで OIDC プロバイダ・デプロイ用ロール・Lambda 実行ロール・ECR リポジトリ・S3 バケットを
作りましたが、**Lambda 関数そのものはまだ作っていません。** 意図的です。

Lambda のコンテナイメージ関数は、ECR に**イメージが実際に push されて存在している**状態で
なければ作成できません。イメージを作るには `docker build` が要り、CloudShell には Docker が
入っていません（2章の前提を参照）。つまりこの CloudShell 上の一度きりの作業では、
そもそもイメージを用意できないため、関数を作ることもできません。

代わりに、**Lambda 関数は Stage 8 のデプロイワークフローが初回実行時に作成し、
2回目以降は更新します。** そのため、3.6 節のデプロイ用ロールの権限には
`lambda:UpdateFunctionCode` だけでなく `lambda:CreateFunction` と、実行ロールを
渡すための `iam:PassRole` も含めています。学習者側でやることは、ここまでの
準備だけです。

**`CreateFunction` にはイメージの push とは別の ECR 権限も要ります。** コンテナイメージの
Lambda 関数を新規作成すると、Lambda は「自分自身がこの ECR リポジトリからイメージを
取得してよい」というリソースベースポリシー（`LambdaECRImageRetrievalPolicy`）を
そのリポジトリに自動で設定しようとします。この自動設定を行うには、`CreateFunction` を
呼ぶ側（＝デプロイ用ロール）が `ecr:GetRepositoryPolicy` と `ecr:SetRepositoryPolicy` を
持っている必要があり、Lambda が設定するポリシーの中身が `ecr:BatchGetImage` と
`ecr:GetDownloadUrlForLayer` を含むため、呼び出し側にも同じ2つの権限が要ります。
これが3.6節の `EcrPushAndImageRetrievalSetup` に push 用の5アクションだけでなく
この4つも入っている理由です。ここが抜けていると、**イメージの push 自体は成功するのに、
`CreateFunction` の呼び出しだけが ECR 権限エラーで失敗する**という、原因を特定しにくい
壊れ方をします。

## 4. 確認

ここまでで作成したものを一覧にします。実際の値をこの表の形で控えておくと、
後片付け（6章）のときにも、Task 10 で困ったときにも役立ちます。

```bash
echo "OIDC provider ARN : $OIDC_PROVIDER_ARN"
echo "Deploy role ARN   : $DEPLOY_ROLE_ARN"
echo "Exec role ARN     : $EXEC_ROLE_ARN"
echo "Exec role name    : $EXEC_ROLE_NAME"
echo "ECR repository ARN: $ECR_REPO_ARN"
echo "ECR repository URI: ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO_NAME}"
echo "S3 bucket name    : $BUCKET_NAME"
echo "Region            : $REGION"
```

| リソース | 名前 / ARN |
|---|---|
| OIDC プロバイダ | `arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com` |
| デプロイ用ロール | `github-actions-sales-report`（`arn:aws:iam::<ACCOUNT_ID>:role/github-actions-sales-report`） |
| Lambda 実行ロール | `sales-report-etl-lambda-role`（`arn:aws:iam::<ACCOUNT_ID>:role/sales-report-etl-lambda-role`） |
| ECR リポジトリ | `sales-report`（`<ACCOUNT_ID>.dkr.ecr.ap-northeast-1.amazonaws.com/sales-report`） |
| S3 バケット | `sales-report-etl-<ACCOUNT_ID>` |
| Lambda 関数 | まだ無い（Stage 8 のワークフロー初回実行で作成される） |

## 5. 私に渡すもの

以下の4つの値を、私（Task 10 でリポジトリのシークレット／変数として設定します）に
伝えてください。

| 値 | 種類 | 内容 |
|---|---|---|
| `AWS_ROLE_ARN` | シークレット | `$DEPLOY_ROLE_ARN`（`arn:aws:iam::<ACCOUNT_ID>:role/github-actions-sales-report`） |
| `AWS_REGION` | 変数 | `ap-northeast-1` |
| `ECR_REPOSITORY` | 変数 | `sales-report` |
| `LAMBDA_FUNCTION_NAME` | 変数 | `sales-report-etl` |

**`AWS_ROLE_ARN` にはあなたの AWS アカウント ID が含まれています。** このリポジトリは
public なので、Issue のコメントや PR の本文など、誰でも読める場所には貼らないでください。
GitHub Actions のシークレットとして設定すれば十分で、それ以外の場所に書き写す必要は
ありません。

## 6. 後片付け

学習が終わったら、課金を止めるために作成したものをすべて削除します。**削除には順序があります**
（バケットが空でないと削除できない、ロールに権限が付いたままだと削除できない、など）。

**新しい CloudShell セッションで実行する場合の注意**: `export` した変数はセッションを
閉じると消えます。3.0 節と同じ内容をもう一度実行してから（`ACCOUNT_ID` は
`aws sts get-caller-identity` で取り直され、他の変数は固定の名前なので同じ値に戻ります）、
以下を実行してください。

```bash
# 1. Lambda 関数（Stage 8 でワークフローが作っていれば削除する。無ければこのコマンドは失敗するので無視してよい）
aws lambda delete-function --function-name "$FUNCTION_NAME" --region "$REGION"

# 2. ECR リポジトリ（--force で中のイメージごと削除する）
aws ecr delete-repository --repository-name "$ECR_REPO_NAME" --force --region "$REGION"

# 3. S3 バケット（先に中身を空にしてからでないと削除できない）
aws s3 rm "s3://${BUCKET_NAME}" --recursive
aws s3api delete-bucket --bucket "$BUCKET_NAME" --region "$REGION"

# 4. デプロイ用ロール（先にインラインポリシーを外してからでないと削除できない）
aws iam delete-role-policy --role-name "$DEPLOY_ROLE_NAME" --policy-name sales-report-deploy-permissions
aws iam delete-role --role-name "$DEPLOY_ROLE_NAME"

# 5. Lambda 実行ロール（管理ポリシーのデタッチとインラインポリシーの削除の両方が必要）
aws iam detach-role-policy --role-name "$EXEC_ROLE_NAME" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
aws iam delete-role-policy --role-name "$EXEC_ROLE_NAME" --policy-name sales-report-etl-s3-access
aws iam delete-role --role-name "$EXEC_ROLE_NAME"

# 6. OIDC プロバイダ（この AWS アカウントで GitHub Actions 連携を他に使っていないことを確認してから）
aws iam delete-open-id-connect-provider --open-id-connect-provider-arn "$OIDC_PROVIDER_ARN"
```

6番目の OIDC プロバイダは、**同じ AWS アカウントで他のリポジトリの GitHub Actions
連携にも使っている場合は削除しないでください。** 削除すると、それらのロールも
一斉に認証できなくなります。このアカウントをこの教材専用に使っている場合は、
削除して問題ありません。
