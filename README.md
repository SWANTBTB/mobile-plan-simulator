# 携帯料金比較シミュレーター
**Mobile Plan Simulator**

[![Tests](https://github.com/SWANTBTB/mobile-plan-simulator/actions/workflows/tests.yml/badge.svg)](https://github.com/SWANTBTB/mobile-plan-simulator/actions/workflows/tests.yml)

---

## 公開デモ

**https://mobile-plan-simulator.onrender.com**

Render Free で公開しています。一定時間アクセスがないとサービスがスリープし、初回表示に数十秒〜1分程度かかる場合があります。

---

## 概要

SoftBank / ワイモバイル / au / UQ mobile / docomo / ahamo / Rakuten Mobile の **7ブランド** について、利用条件から料金を計算・横断比較する Web アプリです。

基本料金表の並べ替えではなく、次のような条件を組み合わせて評価します。

- データ使用量・年齢
- 単回線 / 複数回線
- 家族割・セット割・カード割
- QR 決済利用額とポイント / キャッシュ還元
- プラン込みの付帯サービス価値

入力ページでは選択中キャリアの料金内訳を確認でき、比較ページでは 7 社を同一条件で並べて確認できます。

---

## 制作背景

携帯料金は、基本料金・各種割引・家族構成・決済方法・ポイント還元・付帯サービスが重なり、単純な料金表だけでは比較しづらい領域です。

本プロジェクトでは、**同じ利用条件を入力するだけで複数ブランドを横断比較できるシミュレーター** を Flask で実装しました。料金データは JSON で管理し、計算ロジックと表示処理を分離してテスト可能な構成にしています。

---

## 主な機能

実装済みの機能のみを記載しています。

| カテゴリ | 内容 |
|---|---|
| **7ブランド横断比較** | 同一条件で全キャリアを並列評価 |
| **単回線 / 複数回線** | 回線ごとにキャリア・プラン・割引を個別指定（最大 10 回線） |
| **年齢条件** | 回線ごとの年齢に応じたプラン・割引の適用可否 |
| **データ使用量** | 容量に応じたプラン自動選択（手動指定も可） |
| **家族割** | キャリアごとの世帯回線数を考慮した割引 |
| **セット割** | 光回線セット割などの一括 ON/OFF |
| **カード割** | PayPay カード等の条件 |
| **QR 決済還元** | PayPay / d払い / au PAY 等の月間利用額から還元を概算 |
| **現在料金との比較** | 入力した月額と最安候補の差額（請求額基準） |
| **3軸比較** | 請求額 / 還元込み実質 / 付帯価値込みの独立最適化 |
| **ブランド内プラン最適化** | 同一ブランドでも評価軸ごとに最適プランが異なる場合を表示 |
| **入力条件の共有** | URL クエリおよび sessionStorage による条件の引き継ぎ |

---

## 3軸比較

本アプリの特徴は、次の 3 指標を **分離して計算・最適化** している点です。

```
請求額（billing_total）
  ↓  ポイント・キャッシュ還元を差し引く
還元込み実質負担（effective_total）
  ↓  付帯サービス価値を差し引く
付帯価値込み参考値（value_adjusted_total）
```

| 指標 | 意味 |
|---|---|
| **請求額** | 実際の請求ベース（基本料金 − 請求時割引。還元は含まない） |
| **還元込み実質負担** | 請求額 − ポイント / キャッシュ還元 |
| **付帯価値込み参考値** | 実質負担 − プラン込み特典の参考価値 |

比較ページでは、各ブランド内で上記 3 軸それぞれ **独立して最安プラン構成** を探索します。同一ブランドでも軸によって最適プランが異なる場合（例: SoftBank で請求額最安と還元込み最安が別プラン）は、軸ごとに分けて表示します。異なる軸の値を同一プラン結果として混在させない設計です。

入力ページ（STEP3）では、選択中キャリアの代表として **請求額最安プラン** を 1 件表示します。

---

## 技術スタック

| レイヤ | 技術 |
|---|---|
| **Backend** | Python, Flask |
| **Frontend** | HTML, JavaScript, Tailwind CSS（CDN） |
| **Template** | Jinja2 |
| **Server** | Waitress（WSGI） |
| **Hosting** | Render（Free Web Service） |
| **Testing** | pytest |
| **Version Control** | Git / GitHub |
| **Data** | JSON（`data/carriers/`） |

---

## システム構成

```
Browser（入力 / 比較 UI）
    ↓  HTTP
Flask（app.py）
    ↓
services/calculator.py（料金計算・比較エンジン）
    ↓
data/carriers/*.json（各社プラン・割引・還元定義）
    ↓
計算結果（JSON）
    ↓
templates / static/js（表示）
```

- **入力ページ** — `/` … `/api/calculate` で選択中キャリアの料金を計算
- **比較ページ** — `/compare` … `/api/compare` で 7 社横断比較
- **永続 DB なし** — 入力内容はサーバーに保存せず、比較条件はブラウザの sessionStorage に一時保持

---

## 技術的に工夫した点

- **料金計算と表示の分離** — 計算は Python（`calculator.py`）、比較 UI は API 返却値をそのまま描画（フロントでの再計算なし）
- **料金データの JSON 管理** — 金額・割引条件をコードにハードコードせず、キャリア JSON を単一情報源とする
- **複数回線の世帯評価** — 家族割など回線数依存の割引を、リクエスト内の回線構成から集計
- **ブランド内のプラン組み合わせ探索** — 複数回線時は eligible なプラン構成を評価し、軸ごとに最適解を選択
- **3 軸の独立最適化** — billing / effective / value_adjusted を別々に最適化し、`axis_quotes` として API 返却
- **軸間の混在防止** — 比較結果のトップレベル各フィールドは、対応する軸の quote と整合
- **テストによる回帰防止** — 料金計算・API・3 軸選択・現行契約差額などを pytest で検証

---

## テスト

```powershell
python -m pytest -q
```

**実行結果（2026-08-24 時点）**

| 結果 | 件数 |
|---|---|
| PASS | **342** |
| SKIP | **33** |
| FAIL | **0** |

SKIP 33 件は、Node.js 未導入環境での UI DOM レンダリングテストです。料金計算・API のテストはすべて PASS しています。

---

## ディレクトリ構成

```
├── app.py                 # Flask ルーティング・API
├── config.py              # 環境別設定
├── wsgi.py                # 本番 WSGI エントリ
├── render.yaml            # Render デプロイ定義
├── requirements.txt
├── services/
│   ├── calculator.py      # 料金計算・3軸比較エンジン
│   ├── carrier_explanation.py
│   ├── current_savings.py
│   └── data_loader.py
├── data/carriers/         # 各社料金 JSON
├── templates/             # Jinja2 テンプレート
├── static/js/             # フロントエンド
└── tests/                 # pytest
```

---

## ローカル実行

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

ブラウザで http://127.0.0.1:5000 を開きます。

環境変数の例は `.env.example` を参照してください。本番用の `SECRET_KEY` 等の実値は README には記載しません。

---

## 本番環境

- **Hosting**: Render Free Web Service
- **Process**: Waitress（`wsgi:app`）
- **URL**: https://mobile-plan-simulator.onrender.com

---

## 注意事項

- **料金基準日**: 2026年8月21日時点（各キャリア JSON の `updated_at` に基づく）
- 本アプリの結果は **参考値** です。契約時の確定料金ではありません
- 料金・割引・キャンペーン・還元条件は変更される場合があります。**契約前に各社公式サイトで最新条件を確認してください**
- 一部の期間限定キャンペーン、通常ポイント還元、決済方法の細分化などは簡略化または未対応です

---

## 今後の改善候補

- 通常ポイント還元ロジックの拡張
- 決済方法条件の詳細化
- 料金 JSON の定期更新運用
- Node.js 導入による UI DOM テストの CI 実行
- 複数回線・多軸探索時のパフォーマンス改善

---

## API（参考）

| エンドポイント | 用途 |
|---|---|
| `GET\|POST /api/calculate` | 入力中キャリアの料金計算 |
| `GET\|POST /api/compare` | 7 社横断比較（3 軸） |
| `GET /api/carriers` | キャリア JSON と UI 設定 |

不正入力は HTTP 400 で JSON エラーを返します。
