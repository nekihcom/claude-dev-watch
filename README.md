# claude-dev-watch

claude.dev ブログの新着記事を毎日検知して DeepL で日本語訳し、GitHub Pages で公開する。

- 新着検知：`https://claude.dev/rss.xml`
- 訳文の保存先：`content/<slug>.json`（1 記事 1 ファイル。Actions がコミットする）
- 重複判定：`content/` に同じ URL の訳文があるかどうか
- 公開：`content/` から記事ページと一覧ページを生成し、GitHub Pages にデプロイする
- 実行：GitHub Actions（毎日 00:00 JST）
- 通知：新しい記事を公開したら ntfy で iPhone に通知する

訳文は HTML ではなく中間表現（JSON）で保存している。ページのデザインを変えたときに、DeepL で翻訳し直さずにサイト全体を作り直せるようにするためである。

## セットアップ

### 1. DeepL

DeepL API Free に登録し、API キーを発行する。

### 2. GitHub

1. リポジトリを public にする（GitHub Free プランでは private リポジトリで Pages を使えない）
2. Settings → Pages → Build and deployment の Source を「GitHub Actions」にする
3. Settings → Secrets and variables → Actions に次を登録する

| Secret | 内容 |
|---|---|
| `DEEPL_API_KEY` | DeepL の API キー |
| `DEEPL_GLOSSARY_ID` | （任意）DeepL 用語集の ID |
| `NTFY_TOPIC` | （任意）ntfy のトピック名。未設定なら通知しない |
| `NTFY_SERVER` | （任意）ntfy サーバーの URL（既定 `https://ntfy.sh`） |

公開 URL は `https://<owner>.github.io/<repo>/` になる。

### 3. ntfy（任意）

1. iPhone に ntfy アプリを入れる
2. 推測されにくいトピック名（例：`claude-dev-watch-` の後にランダムな文字列）を決め、アプリで購読する。ntfy.sh のトピックはトピック名を知っていれば誰でも購読・送信できるため、トピック名を Secret として扱う
3. 決めたトピック名を `NTFY_TOPIC` に登録する

## ローカル実行

```sh
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
cp .env.example .env && chmod 600 .env   # .env に DEEPL_API_KEY を書く
```

API キーなどはリポジトリ直下の `.env`（`.env.example` を参照）から読み込む。環境変数が既に設定されていれば、そちらを優先する。`.env` はコミットしない。

```sh
# 翻訳せずに構造だけを確認する（API キー不要）
.venv/bin/claude-dev-watch --dry-run --no-translate --limit 1

# 翻訳して Markdown を out/ に出力する（content/ には保存しない）
.venv/bin/claude-dev-watch --dry-run --limit 1

# 翻訳して content/ に保存する
.venv/bin/claude-dev-watch --limit 1

# content/ からサイトを _site/ に生成する
.venv/bin/claude-dev-watch build-site

# 保存済みの訳文の図（SVG）を原文から補う（DeepL は呼ばない）
.venv/bin/claude-dev-watch refresh-figures
open _site/index.html

# 指定した訳文を新着として ntfy で通知する（.env の NTFY_TOPIC を使う）
.venv/bin/claude-dev-watch notify --site-url https://<owner>.github.io/<repo>/ content/<slug>.json
```

コマンドはリポジトリ直下で実行する（`.env` をカレントディレクトリから探すため）。

| オプション | 内容 |
|---|---|
| `--content DIR` | 訳文の保存先（既定 `content/`）。`build-site` の読み込み元にもなる。サブコマンドより前に書く |
| `--dry-run` | 訳文を保存せず、Markdown を `--out`（既定 `out/`）に出力する |
| `--limit N` | 未保存の記事のうち、古い順に N 件だけ処理する |
| `--url URL` | 指定した記事だけを処理する |
| `--no-translate` | DeepL を呼ばずに原文のまま処理する |
| `build-site --site-out DIR` | サイトの出力先（既定 `_site/`） |
| `notify --site-url URL FILE...` | `FILE` を新着として通知する。通知をタップすると、1 件ならその記事、2 件以上なら一覧ページを開く |

## 動作

1. RSS から記事一覧を取得し、`content/` に未保存の記事だけを古い順に処理する
2. 記事ページの `div#body` から本文を取り出す。コードブロックは翻訳しない
3. DeepL の残り文字数が足りなければ、その記事以降は処理せずに警告を出す（失敗扱いにはしない）。残りは翌月以降の実行で処理する
4. 1 記事の失敗で全体は止めない。失敗が 1 件でもあれば終了コード 1 で終わり、Actions が失敗通知を出す
5. 訳し終えた記事は、ほかの記事が失敗しても `content/` にコミットし、サイトに反映する
6. `content/` に新しい訳文が追加され、サイトの公開に成功したら、ntfy で「新着 N 件」と通知する。既存の訳文の更新だけでは通知しない

SVG の図やインタラクティブな可視化は再現できないため、原文の参照を促す注記に置き換える。画像と動画は原文サイトのファイルを表示する。

訳文の HTML は DeepL を経由しているため、ページに出力する前に、許可したインラインタグ（リンク・強調・コードなど）と http(s) のリンク以外を取り除く。

## 運用上の注意

- 記事を作り直したいときは `content/<slug>.json` を削除してコミットする。次回の実行で翻訳し直す
- 翻訳できるのは RSS に載っている記事だけである
- GitHub Actions の cron は、リポジトリに 60 日間コミットがないと停止する。新着記事がない期間が続くと止まるので、Actions 画面から再有効化する
- cron は混雑時に数分〜数十分遅れて実行されることがある

## テスト

```sh
.venv/bin/pytest
```
