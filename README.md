# Rpi-Multi-Device-HID-Proxy

Raspberry Pi を使用して、複数のキーボード・マウスを1つのUSB HIDデバイスとして中継するプロキシシステムです。

## 概要

このプロジェクトは、Raspberry Pi（特にZero 2W）をUSB HIDガジェットとして設定し、接続された複数の入力デバイス（キーボード、マウス）を統合して、ホストPCに1つのHIDデバイスとして出力します。

### 主な機能

- **マルチデバイス対応**: 複数のキーボード・マウスを同時に接続可能
- **キーリマップ**: キーボード入力のリマッピング機能
- **GPIOボタン制御**: 物理ボタンによるモード切替やマクロ実行
- **NeoPixel LED**: 状態表示用LEDインジケータ
- **高性能マウスプロキシ**: Rust実装による低レイテンシなマウス中継

### 対応デバイス

- HHKB Studio (キーボード・マウス)
- Logitech マウス
- その他のUSB HIDデバイス（udevルール追加で対応可能）

## ディレクトリ構成

```
Rpi-Multi-Device-HID-Proxy/
├── config/                 # 設定ファイル
│   ├── config.json
│   └── config.json.sample
├── docs/                   # ドキュメント
│   ├── BUILD.md
│   ├── INSTALL.md
│   └── CONFIGURATION.md
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

## ライセンス

[LICENSE](LICENSE) ファイルを参照してください。
