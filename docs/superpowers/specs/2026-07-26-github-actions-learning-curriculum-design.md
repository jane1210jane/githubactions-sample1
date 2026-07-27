# GitHub Actions 段階学習リポジトリ 設計書

- 作成日: 2026-07-26
- ステータス: 承認済み（実装計画の作成へ）
- 対象リポジトリ: `githubactions-sample1`

## 1. 目的

GitHub Actions をほぼ未経験の状態から、業務プロジェクトへ適用できるレベルまで段階的に引き上げる。
最終到達点は「プロダクト品質の CI/CD をゼロから設計・運用できること」であり、その過程で作られる
リポジトリの最終形が、そのまま会社プロジェクト向けテンプレートの原型になることを狙う。

### 成功基準

1. 学習者が、未経験の状態から Stage 0 を独力で完了できる。
2. 各ステージの解説を読むだけでも「なぜその設定が必要か」が理解でき、手を動かせばより深く定着する。
3. Stage 11 完了時点のリポジトリを雛形として、会社の新規プロジェクトに CI/CD を導入できる。
4. 掲載された全ワークフローが、GitHub 上で実際に成功実行された実績を持つ。

## 2. 学習者の前提

| 項目 | 内容 |
|---|---|
| GitHub Actions 経験 | ほぼ未経験。YAML 文法にも不安がある |
| 開発環境 | Windows + VSCode、プロジェクトにより WSL2 Ubuntu |
| クラウド | AWS ap-northeast-1、Databricks Free Edition（会社は Azure Databricks） |
| 業務での開発対象 | Python GUI アプリ、Python ETL、Next.js + FastAPI Web アプリ、Databricks パイプライン |

## 3. 全体方針（確定事項）

| 決定事項 | 内容 | 理由 |
|---|---|---|
| 成果物の形 | 育てるハンズオン教材リポジトリ | 手を動かした体験が定着し、最終形が業務資産になる |
| 構成方式 | 積み上げ型（案A）。1 つのアプリを Stage 0→N で育て、各ステージ完了時に git タグを打つ | ワークフローは `.github/workflows/` 直下にしか置けないため、ステージ並置型は実行制御が煩雑になる |
| 学習スタイル | 完成コード + 解説 + 演習課題（解答付き）の 3 点セット | 読むだけでも学べ、深めたい箇所だけ手を動かせる |
| 外部連携 | 段階的に実接続。前半は GitHub 内で完結し、Stage 8 で AWS、Stage 10 で Databricks へ | アカウント準備の負荷を学習の進捗に合わせて分散できる |
| Python 依存管理 | 最初から `uv` 一本 | 現在の主流であり、最終形との差分が少ない |
| リポジトリ公開設定 | public | Actions 実行時間が無制限・無料。バッジや Scorecard も利用できる |
| ローカル実行ツール | `act` 等は採用しない | 本物のランナーとの差異が学習の妨げになる |

### `uv` 採用に伴う補正

`uv` はキャッシュがほぼ自動のため、Stage 3 で `actions/cache` を手で組む学習機会が減る。
これを補うため、以下のとおり配置し直す。

- Stage 3: `uv` のキャッシュが実際に何を保存しているかを**観察**する
- Stage 7: Docker レイヤキャッシュで `actions/cache` を**自作**する
- Stage 9: Playwright ブラウザバイナリのキャッシュで再度**自作**する

## 4. カリキュラム構成

全 12 ステージ + オプション 1 を 4 フェーズに分ける。**各フェーズが独立した「仕様 → 計画 → 実装」サイクル**となる。

### フェーズ 1: 基礎 — Actions の言葉を覚える

| Stage | テーマ | 学習内容 |
|---|---|---|
| 0 | 最小のワークフロー | 実行モデル（イベント → ワークフロー → ジョブ → ステップ）、ランナーは使い捨てという原則、YAML 文法の最小限、Actions タブとログの読み方、`workflow_dispatch` |
| 1 | Python CLI に CI をつける | `actions/checkout`、`astral-sh/setup-uv`、依存インストール、`pytest`、失敗ログの読み解き、ステータスバッジ |
| 2 | トリガー設計と PR ゲート | `push` / `pull_request` の違い、`paths`・`branches` フィルタ、`concurrency` による無駄実行の抑止、ruleset による必須チェック化 |

### フェーズ 2: 実践 CI — 速く・壊れにくく

| Stage | テーマ | 学習内容 |
|---|---|---|
| 3 | 高速化と再現性 | CI 実行時間の実測、`uv` キャッシュの中身の観察、`matrix`（Python 版 × OS）、`fail-fast`、`timeout-minutes`、artifact アップロード、`actionlint` によるワークフロー自体の検査 |
| 4 | 品質ゲート | カバレッジ閾値、型チェック（mypy）、`needs` / `if` / `outputs` によるジョブ連携、`$GITHUB_STEP_SUMMARY` での結果可視化 |
| 5 | 再利用と構造化 | 自作 composite action、`workflow_call` による reusable workflow、共通 CI を複数リポジトリへ配る設計 |

### フェーズ 3: セキュリティとデリバリー

| Stage | テーマ | 学習内容 |
|---|---|---|
| 6 | セキュリティ基礎 | `permissions` の最小化、`pull_request_target` の罠、サードパーティ action の SHA ピン留め、secrets とログマスキング、`zizmor` によるセキュリティ監査（`actionlint` は Stage 3 で導入済み） |
| 7 | ETL 化とコンテナ | CLI を ETL へ発展、Docker ビルド、GHCR への push、`actions/cache` によるレイヤキャッシュ自作 |
| 8 | AWS へ実デプロイ | OIDC による一時認証（長期アクセスキーの廃止）、`environments` と承認フロー、staging → production、ロールバック |

### フェーズ 4: 実務適用

| Stage | テーマ | 学習内容 |
|---|---|---|
| 9 | モノレポ化 | Next.js + FastAPI を追加、変更検知と `paths` による選択実行、Node 依存キャッシュ、Playwright E2E とブラウザキャッシュ自作 |
| 10 | Databricks パイプライン | Databricks Asset Bundles の CI/CD、Free Edition で検証 → Azure Databricks への移植差分 |
| 11 | 運用とプロダクト品質 | タグ → リリース自動化、Renovate / Dependabot、CODEOWNERS、失敗通知、コストと self-hosted runner の判断基準、OpenSSF Scorecard |
| 12（任意） | Python GUI の配布 | Windows ランナー、PyInstaller によるバイナリ生成、リリースへの成果物添付、GUI テストの現実的な線引き |

### ステージ配置の根拠

- **Python GUI を Stage 12（任意）に置く**: GUI の CI 論点は「Windows ランナー + パッケージング + 成果物配布」であり、Actions の中核概念とは独立している。他ステージが依存しないため、必要になった時点で追加できる位置に置く。
- **セキュリティを Stage 6 に置く**: `permissions` や OIDC は、守るべき対象（デプロイ・secrets）が存在しないと必要性が理解できない。Stage 7-8 の直前に置き、翌ステージで即座に使う形にする。ただし Stage 1 の時点から `permissions: contents: read` は記述しておき、**その理由は Stage 6 で回収する**という伏線を張る。
- **ruleset を Stage 2 に置く**: CI は「落ちても無視できる」状態では意味がない。早い段階で「落ちたらマージできない」体験まで到達させる。
- **モノレポ化を Stage 9 まで遅らせる**: `paths` フィルタや変更検知が「なぜ必要か」は、単一構成で困ってからでないと理解できない。移行の痛みを伴う体験として設計する。
- **`actionlint` を Stage 6 から Stage 3 へ前倒しする**（フェーズ1完了後の改訂）: Stage 3 で `matrix` を導入するとワークフローが一気に複雑になり、全組み合わせを目視で確認するのが非現実的になる。ここで「ワークフロー自体も検査対象である」という発想を与える。Stage 6 は `zizmor` によるセキュリティ監査に絞って深める。

## 5. 題材アプリ: `sales-report`

全ステージを通して同一の業務ドメイン（売上 CSV の月次集計）を使う。学習者がアプリ側の理解に労力を割かず、
CI/CD 側の差分だけに集中できるようにするため。

| 段階 | 姿 |
|---|---|
| Stage 1 | CSV を読んで月次集計を標準出力する CLI |
| Stage 7 | S3 から取得 → 変換 → S3 へ書き戻す ETL |
| Stage 9 | 集計結果を返す FastAPI + 表示する Next.js ダッシュボード |
| Stage 10 | 同じ集計ロジックを Databricks パイプライン化 |
| Stage 12 | 集計を実行する Python GUI（配布バイナリ） |

集計ロジックは純粋関数として `packages/core` に切り出し、CLI・API・GUI・Databricks はすべてその薄いラッパーとする。
これは学習の都合であると同時に、実務としても正しい構造である。

### リポジトリ構造

**Stage 1 時点（意図的に最小）**

```
.github/workflows/ci.yml
src/sales_report/{__init__,cli,aggregate}.py
tests/test_aggregate.py
data/sales_sample.csv
pyproject.toml
README.md
docs/stages/stage-00-*.md, stage-01-*.md
```

**Stage 11 時点（最終形 = 会社用テンプレートの原型）**

```
.github/
  workflows/          ci-python.yml, ci-web.yml, deploy-aws.yml, release.yml, ...
  actions/            自作 composite action
apps/       cli/ api/ web/ gui/
packages/   core/          ← 集計ロジック（唯一の真実）
pipelines/  databricks/
infra/      OIDC ロール等の IaC
docs/stages/
```

## 6. ステージの記録と参照方法

各ステージ完了時に `git tag stage-NN` を打つ。学習者は 3 通りの読み方ができる。

- `git checkout stage-03` — その時点の全体像を再現する
- `git diff stage-02..stage-03` — そのステージでの変更点を 1 コマンドで確認する
- `docs/stages/stage-03-*.md` — checkout せずに読める解説（差分の要点を転記済み）

## 7. 解説ドキュメントの固定フォーマット

全ステージ共通の 8 節構成とする。形式が一定であれば、学習者は「どこに何が書いてあるか」を探す必要がない。

1. **このステージのゴール** — できるようになること
2. **前提** — `stage-NN-1` 完了時点であること
3. **なぜ必要か** — 現在の構成で起きている具体的な困りごと
4. **手順** — 手を動かす内容
5. **何が変わったか** — 差分の要点と、各設定行の意味
6. **つまずきポイント** — 実際に踏む罠と、その症状
7. **演習課題** — 解答は `docs/stages/answers/stage-NN.md` に別置き
8. **実務への持ち込みメモ** — 会社プロジェクトへ適用するときの注意

## 8. 1 ステージあたりの成果物（5 点セット）

1. `.github/workflows/` の追加・変更
2. アプリ側の差分（そのステージで必要な分だけ）
3. `docs/stages/stage-NN-*.md`（8 節フォーマット）
4. 演習課題と解答（`docs/stages/answers/stage-NN.md`）
5. `stage-NN` タグ

## 9. 進め方の運用

- **Stage 0–1**: `main` へ直接コミットする（PR の概念をまだ導入していないため）
- **Stage 2 以降**: `stage/NN-<topic>` ブランチ → PR → CI グリーン → マージ

Stage 2 で必須チェックを設定した直後から、学習者自身がそのゲートを毎回通ることになる。
教材の進め方そのものが演習として機能する。

## 10. 検証戦略

教材として最悪の事態は「掲載されたワークフローが実は動かない」ことであるため、二重に確認する。

| 対象 | 方法 |
|---|---|
| ワークフローの構文・式・シェル | `actionlint` を CI に組み込む（Stage 3 で学習対象として導入し、以降は常時稼働させる） |
| ワークフローの実動作 | 各ステージのワークフローを GitHub 上で実行し、成功を確認してから `stage-NN` タグを打つ。解説には実行結果の要点を記載する |
| アプリコード | Stage 1 から `pytest` + カバレッジ 80% 以上を維持。Stage 4 でこれを CI のゲートに昇格させる |
| 解説ドキュメントの行番号引用 | 各ステージ解説に転記したワークフロー YAML と、本文中の「N行目」引用との整合を検査するスクリプトを CI で回す（フェーズ1で3回再発した欠陥への恒久対処。Stage 3 で導入） |

### 解説ドキュメントと実ファイルの関係（フェーズ1完了後の改訂）

各ステージ解説は、そのステージ時点のワークフロー YAML を**本文に転記**し、行番号引用は転記ブロック内を指す。
実ファイルを直接指すと、後続ステージがそのファイルを編集した瞬間に過去の解説が壊れるため。
転記ブロックには、それが `stage-NN` タグ時点の状態であることと、後続ステージで変わる旨を明記する。

## 11. つまずきへの備え

各ステージの「つまずきポイント」節に加えて、`docs/troubleshooting.md` に横断索引を置く。
「症状 → 原因 → 対処」の形式とし、`Error: Process completed with exit code 1` のような
**実際に目にする文字列から引ける**構成にする。ワークフローの失敗はローカルと違ってデバッグしづらく、
最大の挫折要因となるため、ここは手厚く作る。

## 12. 環境前提

- ローカル作業は WSL2 Ubuntu を主とし、Windows ネイティブでも動くようパス依存を避ける
- CI ランナーは `ubuntu-latest` を基本とし、Stage 3 の matrix と Stage 12 で `windows-latest` を扱う
- GitHub 上に public リポジトリを作成し、`origin` として接続する
- **Windows 固有の差異は README の「Windows で進める場合」節に集約する**（フェーズ1完了後の改訂）。
  コンソールの文字コード（`chcp 65001`）、`sed -i` など Git Bash 前提のコマンド、パス区切りの扱いを一箇所にまとめ、
  各ステージ解説からはそこを参照する。ステージごとに同じ注意書きを繰り返さない。

## 13. スコープ外

- 本設計書はカリキュラム全体の骨格を定義する。**各フェーズの詳細な実装計画は、フェーズごとに別途作成する。**
- 直近の実装対象はフェーズ 1（Stage 0–2）のみとする。
- GitLab CI や Jenkins など他 CI ツールとの比較は扱わない。
- AWS / Databricks そのものの入門は扱わない。CI/CD から利用する範囲に限定する。

## 14. 未確定事項（後続フェーズで決定する）

以下は該当フェーズの設計時に決定するため、本設計書では確定させない。

| 項目 | 決定するタイミング |
|---|---|
| Stage 8 の AWS デプロイ先（Lambda / ECS / S3 のいずれか） | フェーズ 3 の設計時 |
| Stage 9 の Next.js ホスティング方式 | フェーズ 4 の設計時 |
| Stage 11 の通知先（Slack / メール / GitHub 通知のみ） | フェーズ 4 の設計時 |
