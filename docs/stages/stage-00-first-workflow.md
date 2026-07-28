# Stage 0: 最初のワークフロー

## 1. このステージのゴール

- GitHub Actions のワークフローファイルを 1 つ作って、実際に動かせる。
- Actions タブでジョブとステップのログを開いて読める。
- `workflow_dispatch` を使って、push を経由せず手動でワークフローを起動できる。

このステージでは新しい概念を覚えるというより、「動くものを 1 回自分の手で作って眺める」ことがゴールです。
細かい用語は次の節でまとめて回収します。

## 2. 前提

- GitHub 上に public リポジトリがあり、`origin` として手元に登録済みであること（Task 1 で完了済み）。
- `gh` CLI がインストールされ、認証済みであること（`gh auth status` で確認できる状態）。
- **ワークフローそのものを実行する**のにローカルの実行環境は一切不要です。`hello.yml` の中身を
  実行するのは自分の PC ではなく GitHub が用意する仮想マシン（ランナー）だからです。
  （ただし Step 2 でローカルに YAML の構文チェックをする際だけは、Python か `uv` のどちらかが必要です。
  詳しくは Step 2 を参照してください。）

## 3. なぜ必要か

GitHub Actions の説明は「YAML を書けばパイプラインが動く」と要約されがちですが、
それを言葉で読むだけでは実感が湧きません。

- 本当に push だけでジョブが起動するのか
- ログはどこで、どんな粒度で見られるのか
- 「ランナー」という言葉が指しているのは具体的に何なのか

これらを一度も自分の目で確認しないまま次のステージ（チェックアウト、依存関係のキャッシュ、
成果物の受け渡しなど）に進むと、すべてが抽象的な知識のまま積み上がってしまいます。
Stage 0 は、その土台となる一次体験を作るためだけに存在します。

## 4. 手順

### Step 1: `hello.yml` を作成する

`.github/workflows/hello.yml` を作成します（本ステージの成果物）。以下は **Stage 0 完了時点
（タグ `stage-00`）の内容をそのまま転記したもの**です。`push:` トリガーは Stage 2 で削除される
ため、現在の `main` の `hello.yml` はこれと異なります（`on:` が `workflow_dispatch:` だけになっています）。
本ドキュメント内の行番号の引用（このステップと次の「5. 何が変わったか」節）は、
すべて**この転記ブロック内の行番号**を指しており、リポジトリの実ファイルを開いて数える必要はありません。

<!-- transcript: .github/workflows/hello.yml @ stage-00 -->
```
  1| # Stage 0: いちばん小さなワークフロー。
  2| # 目的は「動かして、ログを読んで、ランナーの正体を知る」こと。
  3| name: Stage 0 - Hello Actions
  4|
  5| # on: どのイベントでこのワークフローを起動するか。
  6| on:
  7|   # push: どのブランチに push しても起動する（Stage 2 で絞り込む）
  8|   push:
  9|   # workflow_dispatch: Actions タブから手動で起動できるようにする
 10|   workflow_dispatch:
 11|     inputs:
 12|       greeting_target:
 13|         description: 挨拶する相手
 14|         required: false
 15|         default: world
 16|         type: string
 17|
 18| # permissions: このワークフローが GITHUB_TOKEN に許す操作。
 19| # 最小権限にしておく。なぜ必要かは Stage 6 で回収する。
 20| permissions:
 21|   contents: read
 22|
 23| jobs:
 24|   greet:
 25|     name: 挨拶してランナーを観察する
 26|     runs-on: ubuntu-latest
 27|     steps:
 28|       - name: 挨拶する
 29|         # 外部から来る値は run: に直接埋め込まず env: を経由させる。
 30|         # 理由は Stage 6 で回収する。
 31|         env:
 32|           GREETING_TARGET: ${{ inputs.greeting_target || 'world' }}
 33|         run: echo "Hello, ${GREETING_TARGET}!"
 34|
 35|       - name: ランナーの素性を確認する
 36|         run: |
 37|           echo "----- OS -----"
 38|           uname -a
 39|           echo "----- 作業ディレクトリ -----"
 40|           pwd
 41|           echo "----- 作業ディレクトリの中身 -----"
 42|           ls -la
 43|           echo "（リポジトリのファイルが無いことに注目。取得は Stage 1 で行う）"
 44|
 45|       - name: 証拠ファイルを作る
 46|         run: |
 47|           date --iso-8601=seconds > evidence.txt
 48|           cat evidence.txt
 49|
 50|       - name: 同じジョブの中ではファイルが残っていることを確認する
 51|         run: cat evidence.txt
 52|
 53|   check-isolation:
 54|     name: 別ジョブから同じファイルを探す
 55|     runs-on: ubuntu-latest
 56|     # needs: greet ジョブの完了を待つ
 57|     needs: greet
 58|     steps:
 59|       - name: 別ジョブに evidence.txt が存在しないことを確認する
 60|         run: |
 61|           if [ -f evidence.txt ]; then
 62|             echo "見つかってしまった（想定外）"
 63|             exit 1
 64|           fi
 65|           echo "存在しない。ジョブごとにランナーは別のマシンである。"
```

ポイントは次の3点です。

- `hello.yml` の `on:`（6〜16行目）に `push`（7〜8行目）と `workflow_dispatch`（9〜16行目）の両方を指定し、
  自動起動と手動起動の両方を試せるようにしてある。**この `push:` は Stage 2 で削除されるため、
  現在の `main` の `hello.yml` には残っていません**（Step 3・Step 4 の確認結果は、
  Stage 0 完了時点でこの `push:` が存在したことを前提にしています）。
- `workflow_dispatch` には `greeting_target` という入力を1つ用意し、手動実行時に挨拶の相手を変えられるようにしてある。
- `jobs:` の下に `greet` と `check-isolation` という2つのジョブがあり、後者は前者の後片付けの様子を観察するためだけに存在する。

### Step 2: YAML の構文を検証する

コミットする前に、YAML として壊れていないかをローカルで確認します。

```bash
python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/hello.yml',encoding='utf-8'))" && echo OK
```

実行環境に PyYAML が入っていない場合は、`uv` 経由で一時的に取得して実行しても構いません。

```bash
uv run --with pyyaml python -c "import yaml; yaml.safe_load(open('.github/workflows/hello.yml',encoding='utf-8')); print('OK')"
```

どちらの方法でも、標準出力に `OK` が出れば構文エラーはありません。
（本リポジトリでは PyYAML 未導入の環境だったため、後者の `uv run` 経由で検証しました。）

### Step 3: コミットして push し、実行を確認する

```bash
git add .github/workflows/hello.yml
git commit -m "feat: Stage 0 の最小ワークフローを追加"
git push
```

push が終わると、GitHub リポジトリの **Actions タブ** に「Stage 0 - Hello Actions」という
ワークフロー実行が自動的に現れます（Step 1 で転記した `on: push:` の効果です。**この `push:` は
Stage 2 で削除されるため、Stage 2 完了後の `main` では同じ操作をしても自動実行されません**。
手動起動する方法は Step 4 を参照してください）。ブラウザで次を確認してください。

1. Actions タブを開くと、一覧の一番上に今回の実行が表示される。
2. 実行名をクリックすると、`greet` と `check-isolation` の2つのジョブが並んで表示される。
   ジョブ名の左に緑のチェックが付けば成功。
3. `greet` ジョブをクリックすると、`steps:` に書いた4つのステップが上から順に並んでいる。
   各ステップを展開すると、`run:` に書いたコマンドとその標準出力がそのまま見える。
4. `check-isolation` ジョブを開き、最後のステップのログに
   「存在しない。ジョブごとにランナーは別のマシンである。」と出ていることを確認する。

ローカルの CLI からも同様に確認できます。手元では次の実行が観測できました
（`greet` → `check-isolation` の順で成功）。

```
✓ main Stage 0 - Hello Actions · 30204998504
✓ 挨拶してランナーを観察する in 2s
✓ 別ジョブから同じファイルを探す in 4s
```

### Step 4: 手動実行も動くことを確認する

Actions タブの左メニューから「Stage 0 - Hello Actions」を選び、右上の **Run workflow** ボタンを押すと、
`greeting_target` を入力するテキストボックスが現れます。ここに `Actions` と入れて実行すると、
`挨拶する` ステップのログに `Hello, Actions!` と出ます。CLI からは次のコマンドでも同じことができます。

```bash
gh workflow run hello.yml -f greeting_target=Actions
```

手元では実際に `Hello, Actions!` がログに出力されることを確認しました。
一方、Step 3 の push 実行では `greeting_target` を指定していないため `Hello, world!` になります
（`inputs.greeting_target || 'world'` のデフォルト値が使われるため）。

## 5. 何が変わったか

`hello.yml` を書いたことで、以下の用語がすべて具体的な行と対応するようになりました。
以下の行番号は、Step 1 で転記した `hello.yml`（タグ `stage-00` 時点の内容）の行番号です。

- **イベント**（`hello.yml` の `on:` ブロック、6〜16行目）: ワークフローを起動するきっかけ。
  ここでは `push` と `workflow_dispatch` の2種類を登録している
  （`push` は Stage 2 で削除されるため、現在の `main` の `on:` ブロックは `workflow_dispatch` のみ）。
- **ワークフロー**（`hello.yml` というファイルそのもの、1つ）: `on:` に登録したイベントが起きたときに
  実行される、一連のジョブの集まり。ワークフロー名は `name:`（3行目）の `Stage 0 - Hello Actions`。
- **ジョブ**（`jobs:` の子、`greet` と `check-isolation`）: `jobs:` の直下に並ぶ実行単位。
  `needs:` で依存関係を指定しない限り、複数のジョブは並列に走る。
- **ステップ**（各ジョブの `steps:` の子）: ジョブの中で上から順番に実行される単位。
  `greet` ジョブには4つのステップがあり、必ずこの順で実行される。
- **ランナー**（`runs-on: ubuntu-latest`、`greet` と `check-isolation` の両方に書かれている）:
  GitHub が用意する使い捨ての仮想マシン。ジョブが始まるたびに新品が割り当てられ、
  ジョブが終わると（中身ごと）破棄される。「ランナーの素性を確認する」ステップの
  `uname -a` や `pwd` のログは、まさにこの使い捨てマシンの中身を見ている。
- **`run:` と `uses:` の違い**: `hello.yml` のステップはすべて `run:` を使っており、
  ランナーのシェル（bash）でコマンド文字列をそのまま実行している。これに対して `uses:` は
  他人（あるいは GitHub 自身）が作った再利用可能な処理を呼び出す書き方で、Stage 1 で
  `actions/checkout` として初めて登場する。
- **`needs:`**（`check-isolation` ジョブの中、`needs: greet`）: ジョブの実行順序を作る指定。
  これを書かなければ `greet` と `check-isolation` は並列に起動してしまう
  （実際に試した結果は演習の問2を参照）。

`check-isolation` ジョブが成功したという事実そのものが、このステージの一番重要な学びです。
`greet` ジョブが `evidence.txt` を作ったにもかかわらず、`check-isolation` ジョブではそのファイルが
存在しません。これは「ジョブごとにまっさらな新品のランナーが割り当てられる」ことの動く証拠です。

## 6. つまずきポイント

- **症状**: `ランナーの素性を確認する` ステップの `ls -la` を見ても、リポジトリ内のファイル
  （`README.md` など）が1つも表示されない。
  **原因**: ランナーは本当に空の状態で起動する。リポジトリの中身は自動では取得されない。
  自分のコードをランナー上に持ってくるには `actions/checkout` が必要で、これは Stage 1 で扱う。

- **症状**: ワークフローを push しても Actions タブに何も出ず、`git push` 側もエラーが出ないのに
  ワークフローが起動しない。あるいは push 直後に GitHub 上で
  `You have an error in your yaml syntax` のようなメッセージが出る。
  **原因**: たいていインデントの崩れが原因で、特にタブ文字が混ざっていると起きやすい。
  **YAML はタブを許可しない。インデントは必ず半角スペースのみ**を使うこと。
  Step 2 でローカル検証（`yaml.safe_load`）を通しておくと、この種の失敗を push 前に潰せる。

- **症状**: ワークフローファイルを書いたのに、そもそも Actions タブの一覧にワークフロー自体が
  現れない。
  **原因**: ワークフローファイルの置き場所は `.github/workflows/` 直下に固定されている。
  サブディレクトリに入れたり、ファイル名の拡張子を `.yml`/`.yaml` 以外にすると認識されない。

- **症状**: `on:` に `workflow_dispatch:` を書いたはずなのに、Actions タブに
  「Run workflow」ボタンが出てこない。
  **原因**: `workflow_dispatch` によるボタンは、**そのワークフローファイルがデフォルトブランチ
  （通常 `main`）に存在して初めて**表示される。ブランチを切って作業している場合は、まず
  そのブランチを push しただけでは足りず、デフォルトブランチにマージ（今回のように直接
  `main` に push）する必要がある。

## 7. 演習課題

以下の3問は `docs/stages/answers/stage-00.md` に解答（動く YAML 断片つき）があります。
まず自分で予想してから答えを見てください。

1. **問1**: `greet` ジョブに「現在の GitHub リポジトリ名を表示するステップ」を足すには、
   どう書けばよいか。
2. **問2**: `check-isolation` から `needs: greet` を外すと何が起きるか。予想してから、
   実際に外して確かめる。
3. **問3**: わざとステップを失敗させる（`run: exit 1`）と、後続のステップとジョブ全体の
   結果はどうなるか。予想してから、実際に確かめる。

## 8. 実務への持ち込みメモ

このステージで確認した「ランナーはジョブごとに使い捨て」という性質は、実務で一番よく
ハマる落とし穴の元になります。たとえば「ビルドジョブで生成したファイルを、次のテストジョブで
使いたい」というのは自然な発想ですが、そのファイルは何もしなければ次のジョブには存在しません
（今回の `check-isolation` ジョブがまさにその状況を再現しています）。

ジョブをまたいでファイルやデータを渡したい場合は、明示的に次のどちらかの仕組みを使う必要があります。

- **artifact**: ファイルそのものをジョブ間で受け渡す仕組み。
- **job outputs**: 文字列程度の小さな値をジョブ間で受け渡す仕組み。

どちらも Stage 3・Stage 4 で扱います。この制約を知らないまま実務のワークフローを組むと、
「ローカルでは動くのに CI だとなぜかファイルが消える」と原因が分からず悩むことになりがちなので、
このステージで体験した空っぽのランナーの感覚を覚えておいてください。
