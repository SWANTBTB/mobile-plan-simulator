# 料金比較シミュレーター

利用状況・割引条件・決済還元をもとに、主要7ブランド（SoftBank / ワイモバイル / au / UQ mobile / docomo / ahamo / Rakuten Mobile）の携帯料金を、**請求額 / 還元込み実質 / 付帯サービス込み** の3軸で比較する Flask アプリです。

## 主な機能

- **複数回線** — 回線ごとにキャリア・プラン・割引を個別入力
- **STEP3（入力中キャリア）** — 利用条件を満たす中から **請求額（billing_total）最安** の代表プランを自動選択
- **7社比較** — 各ブランド内で billing / effective / value_adjusted を **独立最適化**（`axis_quotes`）
- **現在の契約** — 実際の月額との差額（請求額基準の `savings_summary`）
- **QR決済還元** — PayPay / d払い / au PAY 等
- **家族割・セット割** — 世帯構成を考慮した組み合わせ探索
- **URL / sessionStorage** — 入力条件の共有・比較ページへの受け渡し

## 計算指標（ユーザー向け）

| 内部名 | 意味 |
|---|---|
| `billing_total` | **実際の請求額**（基本料金 − 請求時割引。ポイント還元は含まない） |
| `reward_total` | **還元合計**（POINT + CASH のみ） |
| `effective_total` | **還元込み実質負担** = max(0, 請求額 − 還元) |
| `value_adjusted_total` | **付帯サービス込み比較額** = max(0, 実質 − 込み特典価値) |

## 技術構成

- **Python 3.14**（開発・テストで使用。3.12 以上を推奨）
- **Flask** + **Jinja2**
- **Tailwind CSS**（CDN — 本番でも現行構成で利用。ビルド環境は不要）
- **JSON** 料金データ（`data/carriers/*.json`）
- **pytest** による計算・API テスト
- 本番: **waitress**（WSGI。Windows / Linux 両対応）

## セットアップ

```powershell
cd project
python -m pip install -r requirements.txt
```

任意: `.env.example` を `.env` にコピーして環境変数を設定。

## 起動

### 開発（Flask 組み込みサーバー）

```powershell
python app.py
```

または `start.bat` をダブルクリック。

- デフォルト: `http://127.0.0.1:5000`
- `FLASK_ENV=development`（デフォルト）、`DEBUG=True`

### 本番（waitress — 開発サーバーを本番利用しない）

```powershell
$env:FLASK_ENV = "production"
$env:SECRET_KEY = "長いランダム文字列"
$env:PORT = "5000"
python -m waitress --listen=0.0.0.0:5000 wsgi:app
```

Linux 等で gunicorn を使う場合:

```bash
export FLASK_ENV=production
export SECRET_KEY='...'
gunicorn -w 2 -b 0.0.0.0:5000 wsgi:app
```

## 環境変数

| 変数 | 説明 | 開発デフォルト |
|---|---|---|
| `FLASK_ENV` | `development` / `production` | `development` |
| `FLASK_DEBUG` | 開発時デバッグ（本番では無効） | `1` |
| `SECRET_KEY` | Flask 署名用（**本番必須**） | 開発用ダミー |
| `HOST` | `python app.py` の bind アドレス | `127.0.0.1` |
| `PORT` | ポート | `5000` |
| `ROBOTS_NOINDEX` | `1` で noindex | 開発時 `1` |

## テスト

```powershell
python -m pytest -q
```

### Node.js UI テスト（任意）

33 件の DOM レンダリングテストは **Node.js 必須**（本番実行には不要）。

```powershell
# Node.js インストール後
python -m pytest tests/test_phase6a_compare_ui.py -q
```

## 料金基準日

各キャリア JSON の `updated_at` から自動生成（現行: **2026年8月21日時点**）。
UI フッターおよび STEP3 付近に表示。

## データ更新

`data/carriers/*.json` を編集。金額はコードにハードコードせず JSON のみで管理。
改定時は `updated_at` と `source_note` も更新。

## データの保存について

- **サーバー**: 入力内容を DB 等へ永続保存しない（リクエスト処理のみ）
- **ブラウザ**: 比較条件は **sessionStorage**（タブ内一時保存）

## 既知の制約

- 一部の通常ポイント還元は未計算
- 期間限定キャンペーンは完全再現しない
- PayPay GOLD 連携の翌月適用等、細かい適用タイミング差は簡略化
- Rakuten 利用料ポイントは税別換算
- 料金は基準日時点の参考値（契約確定料金ではない）

## API

- `GET|POST /api/calculate` — 入力中キャリアの料金計算
- `GET|POST /api/compare` — 7社横断比較（3軸）
- `GET /api/carriers` — キャリア JSON + UI 設定

不正入力は `400` + `{"error":"invalid_request",...}`。内部エラーは traceback を返さない。

## ディレクトリ構成

```
project/
├── app.py              # Flask アプリ
├── config.py           # 環境別設定
├── wsgi.py             # 本番 WSGI エントリ
├── data/carriers/      # 料金 JSON
├── services/           # 計算・説明文
├── static/js/          # フロントエンド
├── templates/          # Jinja2
└── tests/
```

## デプロイ候補（未実施 — 参考）

公開先未確定のため、実デプロイは行っていません。Flask + HTTPS + 環境変数対応の例:

| サービス | 特徴 |
|---|---|
| **Render** | Git 連携、無料枠あり、HTTPS 自動 |
| **Railway** | 環境変数・PORT 対応、手軽 |
| **Fly.io** | リージョン選択可、スケールしやすい |

いずれも `waitress` または `gunicorn` + `wsgi:app` を想定。

## 注意

料金・割引・還元条件は変更される場合があります。**契約前に各社公式サイトで最新条件を確認してください。**
