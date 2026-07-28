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

### フェーズ2: 実践 CI — 速く・壊れにくく

| Stage | テーマ | 解説 |
|---|---|---|
| 3 | 高速化と再現性 | [stage-03](docs/stages/stage-03-speed-and-matrix.md) |
| 4 | 品質ゲート | [stage-04](docs/stages/stage-04-quality-gate.md) |
| 5 | 再利用と構造化 | [stage-05](docs/stages/stage-05-reuse.md) |

### フェーズ3以降

フェーズ3（セキュリティ・コンテナ・AWS デプロイ）、フェーズ4（モノレポ・Databricks・運用）は
順次追加します。全体像は [設計書](docs/superpowers/specs/2026-07-26-github-actions-learning-curriculum-design.md) を参照してください。

## Stage 8 に進む前に

Stage 8 では実際に AWS へデプロイします。GitHub Actions が AWS に入るための一度きりの準備が
必要で、これだけは手作業で行います（理由は手順書の冒頭に書いてあります）。
Stage 6・7 を進めながら並行して済ませておくと、Stage 8 で待たされません。

[docs/aws-bootstrap.md](docs/aws-bootstrap.md)

## Windows で進める場合

学習者の環境は Windows + VSCode を想定しています。WSL2 Ubuntu でも進められますが、
Windows ネイティブのターミナルで進める場合は以下に注意してください。

### 日本語が文字化けする

`uv run sales-report data/sales_sample.csv` の出力が `???` や記号の羅列になる場合、
コンソールの文字コードが UTF-8 になっていません。プログラムは壊れていません。

```powershell
chcp 65001                              # コードページを UTF-8 にする
$env:PYTHONIOENCODING = "utf-8"         # あるいは Python 側の出力エンコーディングを指定する
```

VSCode の統合ターミナルでも同様です。設定を変えたくない場合は `uv run pytest` で
テストを走らせれば、出力の中身は正しく検証できます（テストは端末を経由しないため影響を受けません）。

### `sed` などの Unix コマンドが使えない

本教材の手順には `sed -i` のような Unix コマンドが出てきます。これらは
`cmd.exe` や PowerShell では動きません。次のいずれかで実行してください。

- **Git Bash**（Git for Windows に同梱）で実行する — 最も手軽
- **WSL2 Ubuntu** で実行する
- エディタで直接ファイルを書き換える — 何を書き換えるかは各手順に明記してあります

### パス区切り

ワークフローは既定では Linux ランナー（`ubuntu-latest`）上で動きますが、Stage 3 以降は
matrix に `windows-latest` も含まれます。YAML の中のパスは、どちらのランナーでも `/`
で書けます。ローカルのコマンド例も `/` で書いてあります。Git Bash と WSL2 ではそのまま動きます。

## 困ったとき

[docs/troubleshooting.md](docs/troubleshooting.md) に、実際のエラーメッセージから引ける索引があります。
