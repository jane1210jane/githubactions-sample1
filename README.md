# GitHub Actions 段階学習リポジトリ

[![CI](https://github.com/jane1210jane/githubactions-sample1/actions/workflows/ci.yml/badge.svg)](https://github.com/jane1210jane/githubactions-sample1/actions/workflows/ci.yml)

売上 CSV を月次集計するサンプルアプリ `sales-report` を題材に、GitHub Actions を
「最小のワークフロー」から「プロダクト品質の CI/CD」まで段階的に学ぶ教材リポジトリです。

## 使い方

各ステージは `docs/stages/` の解説を読みながら進めます。
過去のステージの状態は git タグで再現できます。

```bash
git checkout stage-01          # Stage 1 完了時点の全体像を再現する
git diff stage-01..stage-02    # Stage 2 で何が変わったかを確認する
git switch main                # 最新の状態に戻る
```

## カリキュラム

### フェーズ1: 基礎 — Actions の言葉を覚える

| Stage | テーマ | 解説 |
|---|---|---|
| 0 | 最小のワークフロー | [stage-00](docs/stages/stage-00-first-workflow.md) |
| 1 | Python CLI に CI をつける | [stage-01](docs/stages/stage-01-python-ci.md) |
| 2 | トリガー設計と PR ゲート | [stage-02](docs/stages/stage-02-triggers-and-pr-gate.md) |

### フェーズ2以降

フェーズ2（高速化・品質ゲート・再利用）、フェーズ3（セキュリティ・コンテナ・AWS デプロイ）、
フェーズ4（モノレポ・Databricks・運用）は順次追加します。
全体像は [設計書](docs/superpowers/specs/2026-07-26-github-actions-learning-curriculum-design.md) を参照してください。

## 困ったとき

[docs/troubleshooting.md](docs/troubleshooting.md) に、実際のエラーメッセージから引ける索引があります。
