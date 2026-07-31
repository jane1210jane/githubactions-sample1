# Stage 8 演習課題 解答

[stage-08-aws-deploy.md](../stage-08-aws-deploy.md) の演習課題3問への解答です。
先に自分で予想してから読んでください。

## 問1: `build` ジョブから `id-token: write` を外すと何が起きるか

**予想**: `id-token: write` は「GitHub の OIDC プロバイダにトークンを発行させてよい」と
いう許可です。これが無ければトークンそのものが手に入らないので、
`aws-actions/configure-aws-credentials` は AWS に渡すべきものを持てません。つまり
**AWS へリクエストが飛ぶ前に**失敗するはずです。信頼ポリシーの `sub` が正しいかどうかとは
無関係に失敗するはずで、`sub` 不一致のときとはエラーの文言も変わるはずです。

**`main` を汚さずに実験する方法**: この演習には仕掛けがあります。`deploy.yml` を直接
書き換えて試そうとすると、`Deploy` は `main` への `push` と `workflow_dispatch` でしか
起動しないため、実験のために `main` を2回（外す・戻す）触ることになります。

しかし、上の予想が正しいなら**この失敗はブランチに依存しません**。`sub` の検証まで
到達しないからです。そこで、実験専用の一時ワークフローを実験用ブランチに置き、
`push` で起動させれば `main` に何も残りません。実際に使ったファイルは次のものです。

```yaml
name: OIDC Experiment

on:
  push:
    branches: [experiment/oidc-id-token]

permissions:
  contents: read

jobs:
  no-id-token:
    name: id-token なしで AWS 認証を試す
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions:
      contents: read
      # id-token: write を意図的に付けない。これが問1の実験そのもの。
    steps:
      - name: AWS の一時認証を取得しようとする
        uses: aws-actions/configure-aws-credentials@e6de054238d6b7531b4efff3b6587d9aade6a06c # v6.2.3
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ vars.AWS_REGION }}
          mask-aws-account-id: "true"
```

この方法が成立するのは、`CI` と `Container` がどちらも `main` への `push` と `main` への
`pull_request` でしか起動しないため、実験用ブランチへの push では他のワークフローが
一切動かないからです。

**実測**（実行 `30593597461`）: 予想どおり AWS に到達せずに失敗しました。

```
It looks like you might be trying to authenticate with OIDC. Did you mean to set the
`id-token` permission? If you are not trying to authenticate with OIDC and the action
is working successfully, you can ignore this message.

Retry validateCredentials: attempt 1 of 12 failed: Credentials could not be loaded,
please check your action inputs: Could not load credentials from any providers.
Retrying after 32ms.
...
Retry validateCredentials: reached max retries (12); giving up.
##[error]Credentials could not be loaded, please check your action inputs:
Could not load credentials from any providers
```

3つ注目してください。

1. **action 自身が `id-token` permission を疑うヒントを出しています。** ただしこれは
   `##[error]` ではなく通常のログ行なので、失敗したステップのログを末尾だけ見ると
   見落とします。
2. **12回リトライして約80秒かかってから諦めます**（00:27:47 開始 → 00:29:09 終了）。
   一時的なネットワーク障害と誤解しやすい挙動です。
3. **エラーの文言が `sub` 不一致のとき（`Not authorized to perform
   sts:AssumeRoleWithWebIdentity`）と全く違います。** 前者は「AWS に到達すらしていない」、
   後者は「AWS まで到達したが断られた」であり、直すべき場所が GitHub 側と AWS 側に
   分かれます。

確認後、実験用ブランチはリモート・ローカルとも削除しました。`main` の履歴には何も
残っていません。

## 問2: `rollback_to_version` を指定してロールバックする

**予想**: Lambda のバージョンは不変で、エイリアスは可変です。`production` エイリアスを
1つ前のバージョン番号へ向け直せば、イメージのビルドも push も行わずに以前の状態へ
戻るはずです。所要時間は `deploy-production` ジョブの実測（11秒）と同程度で、`build` と
`deploy-staging` も走るぶんだけ全体では長くなるはずです。

`deploy.yml` の該当箇所は、`on.workflow_dispatch.inputs.rollback_to_version` の入力定義と、
`deploy-production` ジョブの「production エイリアスを張り替える」ステップの分岐です
（行番号付きの転記は[解説の第5節](../stage-08-aws-deploy.md)にあります）。入力が空でなければ
その番号を、空なら `staging` と同じ番号を `production` へ向けます。

**手順**:

```bash
# 現在の状態を確認する（AWS CloudShell）
aws lambda list-versions-by-function --function-name sales-report-etl \
  --query 'Versions[].Version' --output text
aws lambda get-alias --function-name sales-report-etl --name production \
  --query FunctionVersion --output text

# 1つ前のバージョンへ戻す（GitHub CLI）
gh workflow run deploy.yml --ref main -f rollback_to_version=1

# production の承認後、戻ったことを確認する
aws lambda get-alias --function-name sales-report-etl --name production \
  --query FunctionVersion --output text
```

**実測**: この解答は Stage 8 の解説をマージした直後に実施し、結果をここに追記します。
実施していない時点でこの節を読んだ場合、**まだ実測されていない**と理解してください。
ロールバックは「試したことがある人」しか本番でできないので、読んで納得するだけで
済ませないでください。

## 問3: `deploy-production` から `environment: production` を消すと何が起きるか

**この問いは実行しません。** 承認を外した状態で本番が更新されてしまうためです。以下は
予想と、その根拠です。

**予想**: 起きることは2つあり、片方は起きません。

1. **承認待ちが消えます。** `production` environment に設定した `required_reviewers` は
   environment に紐づく保護ルールなので、ジョブが environment を参照しなくなれば適用
   されません。`deploy-staging` が終わった瞬間に `deploy-production` が走り、本番の
   エイリアスが更新されます。実測では承認待ちに約5時間55分かかっていましたが、その
   停止が無くなり、11秒で本番が変わります。
2. **デプロイ可能ブランチの制限も外れます。** environment に設定したブランチ制限も
   environment に紐づくものなので、同時に効かなくなります。
3. **OIDC の認証は通ってしまいます。** ここが最も見落としやすい点です。`environment:` が
   無くなると、そのジョブのトークンの `sub` は `<prefix>:environment:production` ではなく
   `<prefix>:ref:refs/heads/main` になります。**この値もこのリポジトリの信頼ポリシーが
   許可しているため、認証は成功します。** つまり AWS 側は何も止めてくれません。

3の裏返しとして、**もし信頼ポリシーが environment 形式の2つだけを許可していたなら、
`environment:` を外した瞬間に認証が落ち、事故は AWS 側で止まっていた**ことになります。

ここから読み取れる設計上の示唆があります。**「承認を挟む」ことと「その環境向けの認証を
許す」ことを同じ environment に紐づけておくと、承認を外す変更が認証の失敗として現れ、
気づける可能性が上がります。** 実務への持ち込みメモに書いた「ロールを環境ごとに分ける」は、
最小権限のためだけでなく、この検知のためでもあります。

なお、`environment:` を消しても**リポジトリのシークレット `AWS_ROLE_ARN` は引き続き
読めます**。environment シークレット（environment に紐づけて設定するシークレット）を
使っていた場合は話が別で、そちらは environment を外すと読めなくなります。この教材では
リポジトリレベルのシークレットを使っているため、その保護は働きません。
