# claude-dev-watch

claude.dev ブログの新着記事を毎日検知し、DeepL で日本語訳した本文を Notion データベースに登録する。

- 新着検知：`https://claude.dev/rss.xml`
- 重複判定：Notion DB の「URL」プロパティ（状態ファイルは持たない）
- 実行：GitHub Actions（毎日 00:00 JST）

訳文は個人・社内での閲覧用である。Notion ページを外部に公開しないこと。

## セットアップ

### 1. DeepL

DeepL API Free に登録し、API キーを発行する。

### 2. Notion

1. https://www.notion.so/profile/integrations で internal インテグレーションを作成し、トークンを控える
2. DB を置く親ページを作り、ページ右上の「…」→「接続」からインテグレーションを追加する
3. DB を作成する（手動で作る場合は下表のプロパティ名・型に合わせる）

```sh
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
cp .env.example .env && chmod 600 .env   # .env に NOTION_TOKEN を書く
.venv/bin/python scripts/create_database.py <親ページの URL>
# → NOTION_DATABASE_ID=... が表示されるので .env に追記する
```

| プロパティ | 型 |
|---|---|
| タイトル | title |
| 原題 | rich_text |
| URL | url |
| 公開日 | date |
| 著者 | rich_text |
| カテゴリ | select |
| 要約 | rich_text |
| 登録日時 | date |

### 3. GitHub

private リポジトリを作成し、Settings → Secrets and variables → Actions に次を登録する。

| Secret | 内容 |
|---|---|
| `DEEPL_API_KEY` | DeepL の API キー |
| `NOTION_TOKEN` | Notion インテグレーションのトークン |
| `NOTION_DATABASE_ID` | 手順 2 で表示された ID |
| `DEEPL_GLOSSARY_ID` | （任意）DeepL 用語集の ID |

## ローカル実行

API キーなどはリポジトリ直下の `.env`（`.env.example` を参照）から読み込む。環境変数が既に設定されていれば、そちらを優先する。`.env` はコミットしない。

```sh
# 翻訳せずに構造だけを確認する（API キー不要）
.venv/bin/claude-dev-watch --dry-run --no-translate --limit 1

# 翻訳して Markdown を out/ に出力する（Notion には書き込まない）
.venv/bin/claude-dev-watch --dry-run --limit 1

# Notion に登録する
.venv/bin/claude-dev-watch --limit 1
```

コマンドはリポジトリ直下で実行する（`.env` をカレントディレクトリから探すため）。

| オプション | 内容 |
|---|---|
| `--dry-run` | Notion に書き込まず、Markdown を `--out`（既定 `out/`）に出力する |
| `--limit N` | 未登録の記事のうち、古い順に N 件だけ処理する |
| `--url URL` | 指定した記事だけを処理する |
| `--no-translate` | DeepL を呼ばずに原文のまま処理する |

## 動作

1. RSS から記事一覧を取得し、Notion に未登録の記事だけを古い順に処理する
2. 記事ページの `div#body` から本文を取り出す。コードブロックは翻訳しない
3. DeepL の残り文字数が足りなければ、その記事以降は処理せずに警告を出す（失敗扱いにはしない）
4. 1 記事の失敗で全体は止めない。失敗が 1 件でもあれば終了コード 1 で終わり、Actions が失敗通知を出す
5. 本文の追加が途中で失敗したページはゴミ箱に移し、次回の実行で作り直す

SVG の図やインタラクティブな可視化は Notion で再現できないため、「図（原文を参照）」の注記に置き換える。動画は原文サイトへのリンクにする。

## 運用上の注意

- GitHub Actions の cron は、リポジトリに 60 日間コミットがないと停止する。停止したら Actions 画面から再有効化する
- cron は混雑時に数分〜数十分遅れて実行されることがある

## テスト

```sh
.venv/bin/pytest
```
