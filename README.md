# LogMap - Amateur Radio Digital Dashboard

アマチュア無線の公開運用向けデジタルダッシュボード。交信した局をリアルタイムで地図上に表示し、統計情報を更新します。

A digital dashboard for public amateur radio operations. Displays contacted stations on a map in real-time with live statistics.

## Features / 機能

- **リアルタイム地図表示** - 交信した局をGoogle Maps上にピン表示
- **ミニパネル** - コールサイン、位置、距離、バンドをポストイット風に表示
- **統計情報** - 総交信局数、最遠局情報をリアルタイム更新
- **多言語対応** - 日本語・英語のUI切り替え
- **自動ズーム** - 全ての交信局が収まるよう自動調整
- **日付変更対応** - 0時を跨ぐとドットを自動消去

## Requirements / 必要環境

- Windows 11
- Python 3.11+
- [Turbo HAMLOG](https://www.hamlog.com/)
- Google Maps API Key

## Setup / セットアップ

### 1. Install dependencies / 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 2. Download cty.dat / cty.datのダウンロード

[Big CTY](https://www.country-files.com/bigcty/) からダウンロードし、`data/cty.dat` に配置してください。

### 3. Configuration / 設定

```bash
copy config.yaml.example config.yaml
```

`config.yaml` を編集して以下を設定:

- `google_maps.api_key` - Google Maps JavaScript API キー
- `station.callsign` - 自局コールサイン
- `station.latitude` / `station.longitude` - 自局の緯度経度
- `hamlog.data_dir` - Turbo HAMLOGのデータディレクトリ
- `dashboard.language` - 表示言語 (`ja` or `en`)

### 4. Run / 実行

```bash
python run.py
```

ブラウザで `http://localhost:5000` にアクセスしてください。

## Architecture / アーキテクチャ

```
logmap/
├── run.py                  # エントリーポイント
├── config.yaml             # 設定ファイル (外部アクセス設定一元管理)
├── app/
│   ├── server.py           # Flask + SocketIO サーバー
│   ├── i18n/               # 多言語対応
│   │   ├── ja.json         # 日本語
│   │   └── en.json         # English
│   ├── services/
│   │   ├── hamlog_reader.py     # Turbo HAMLOG .hdb ファイル読み取り
│   │   ├── cty_parser.py        # cty.dat パーサー
│   │   ├── jcc_resolver.py      # JCC コード → 位置情報
│   │   ├── location_resolver.py # 位置特定 (JCC/Grid/CTY)
│   │   ├── geo_utils.py         # 距離計算、グリッドスクエア変換
│   │   └── log_monitor.py       # ログファイル監視
│   ├── static/
│   │   ├── css/dashboard.css
│   │   └── js/dashboard.js
│   └── templates/
│       └── dashboard.html
└── data/                   # cty.dat, JCCデータ等
```

### Location Resolution Priority / 位置特定の優先順位

1. **JCC Code** - 日本国内局で JCC コードがある場合
2. **Grid Square** - FT8等のデジタルモードでグリッドスクエアがある場合
3. **cty.dat** - コールサインプレフィックスから国/地域の中心座標

### External Access Configuration / 外部アクセス設定

全ての外部サービス・ファイルアクセスは `config.yaml` に集約:

- Turbo HAMLOG データベースパス
- cty.dat ファイルパス
- Google Maps API キー
- JCC データファイルパス

## Future Plans / 今後の予定

- [ ] 他のログソフトウェア対応 (Logger32, N1MM+ 等)
- [ ] ADIF ファイル直接読み込み
- [ ] より詳細なJCCコードデータ
- [ ] バンド別の色分け表示
- [ ] 交信時刻のタイムライン表示

## License

MIT License
