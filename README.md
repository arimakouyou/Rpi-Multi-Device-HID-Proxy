# Rpi-Multi-Device-HID-Proxy

Raspberry Pi を使用して、複数のキーボード・マウスを1つのUSB HIDデバイスとして中継するプロキシシステムです。

## 概要

このプロジェクトは、Raspberry Pi（特にZero 2W）をUSB HIDガジェットとして設定し、接続された複数の入力デバイス（キーボード、マウス）を統合して、ホストPCに1つのHIDデバイスとして出力します。

### 主な機能

- **マルチデバイス対応**: 複数のキーボード・マウスを同時に接続可能
- **キーリマップ**: キーボード入力のリマッピング機能
- **GPIOボタン制御**: 物理ボタンによるモード切替やマクロ実行
- **APA102 LED (Pimoroni Keybow Mini)**: SPI 経由で駆動する状態表示用 RGB LED
- **高性能マウスプロキシ**: Rust実装による低レイテンシなマウス中継

### 対応デバイス

- HHKB Studio (キーボード・マウス)
- Logitech マウス
- その他のUSB HIDデバイス（udevルール追加で対応可能）

## ディレクトリ構成

```
Rpi-Multi-Device-HID-Proxy/
├── AGENTS.md               # AI コーディングエージェント向けサマリ
├── config/                 # 設定ファイル
│   ├── config.json
│   └── config.json.sample
├── docs/                   # ドキュメント
│   ├── ARCHITECTURE.md
│   ├── BUILD.md
│   ├── CONFIGURATION.md
│   ├── DEVELOPMENT.md
│   ├── HARDWARE.md
│   └── INSTALL.md
├── rust/                   # Rust ソースコード（マウスプロキシ）
│   └── mouse_proxy_rs/
├── scripts/                # シェルスクリプト
│   ├── build_release.sh
│   ├── install.sh
│   ├── setup_hid_gadget.sh
│   └── uninstall.sh
├── src/                    # Python ソースコード
│   ├── hid_keys.py
│   ├── keyboard_proxy.py
│   └── proxy_core.py
├── systemd/                # systemd サービスファイル
│   ├── keyboard-proxy.service
│   ├── mouse-proxy@.service
│   └── multi-hid-gadget.service
└── udev/                   # udev ルール
    └── 99-mouse-proxy.rules
```

## クイックスタート

### 必要なもの

- Raspberry Pi Zero 2W（またはOTG対応のRaspberry Pi）
- Raspberry Pi OS (Bookworm以降推奨)
- USB OTGケーブル

### インストール

1. リリースアーカイブをダウンロードして展開
2. インストールスクリプトを実行

```bash
tar -xzf multi-hid-proxy-release.tar.gz
cd multi-hid-proxy
sudo ./install.sh
sudo reboot
```

詳細は [docs/INSTALL.md](docs/INSTALL.md) を参照してください。

## ドキュメント

- [インストールガイド](docs/INSTALL.md) - インストール手順と要件
- [ビルドガイド](docs/BUILD.md) - ソースからのビルド方法
- [設定ガイド](docs/CONFIGURATION.md) - 設定ファイルの詳細
- [アーキテクチャ](docs/ARCHITECTURE.md) - 三層構造・起動順序・データフロー・HID レポート仕様
- [ハードウェア配線ガイド](docs/HARDWARE.md) - GPIO ボタン・APA102 LED (Keybow Mini)・USB OTG の物理配線
- [開発者ガイド](docs/DEVELOPMENT.md) - 拡張方法・テスト戦略・PR ガイドライン
- [AGENTS.md](AGENTS.md) - AI コーディングエージェント向けの最短サマリ

## ライセンス

[LICENSE](LICENSE) ファイルを参照してください。
