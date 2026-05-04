# インストールガイド

## システム要件

### ハードウェア

- Raspberry Pi Zero 2W（推奨）またはOTG対応のRaspberry Pi
- microSDカード（8GB以上）
- USB OTGケーブル（データ通信対応）
- （オプション）Pimoroni Keybow Mini（3 キー + APA102 LED 3 個、SPI 経由）

### ソフトウェア

- Raspberry Pi OS Bookworm以降（64-bit推奨）
- Python 3.9以上

## 事前準備

### 1. USB OTGの有効化

`/boot/firmware/config.txt` に以下を追加:

```
dtoverlay=dwc2
```

`/boot/firmware/cmdline.txt` の `rootwait` の後に以下を追加:

```
modules-load=dwc2,libcomposite
```

### 2. 必要なパッケージのインストール

```bash
sudo apt update
sudo apt install -y python3-evdev jq
```

## インストール方法

### 方法1: リリースアーカイブからインストール（推奨）

1. GitHubリリースページからアーカイブをダウンロード

2. 展開してインストール

```bash
tar -xzf multi-hid-proxy-release.tar.gz
cd multi-hid-proxy
sudo ./install.sh
```

3. 再起動

```bash
sudo reboot
```

### 方法2: ソースからインストール

ビルドが必要です。[BUILD.md](BUILD.md) を参照してください。

## インストールされるファイル

| ファイル | インストール先 |
|---------|---------------|
| Python スクリプト | `/usr/local/bin/` |
| mouse_proxy_rs | `/usr/local/bin/` |
| setup_hid_gadget.sh | `/usr/local/bin/` |
| systemd サービス | `/etc/systemd/system/` |
| udev ルール | `/etc/udev/rules.d/` |
| 設定ファイル | `/etc/multi-hid-proxy/config.json` |

## サービスの確認

インストール後、以下のサービスが自動起動します:

```bash
# HIDガジェットのステータス確認
sudo systemctl status multi-hid-gadget.service

# キーボードプロキシのステータス確認
sudo systemctl status keyboard-proxy.service

# マウスプロキシのステータス確認（接続時に自動起動）
sudo systemctl status mouse-proxy@event*.service
```

## トラブルシューティング

### HIDデバイスが作成されない

1. OTG設定を確認

```bash
lsmod | grep dwc2
lsmod | grep libcomposite
```

2. ガジェット設定を確認

```bash
ls -la /dev/hidg*
```

### キーボードが認識されない

1. 接続されているデバイスを確認

```bash
cat /proc/bus/input/devices
```

2. サービスログを確認

```bash
sudo journalctl -u keyboard-proxy.service -f
```

### マウスが認識されない

1. udevルールを確認

```bash
udevadm info /dev/input/eventX
```

2. 必要に応じてudevルールを追加（[CONFIGURATION.md](CONFIGURATION.md) 参照）

## アンインストール

```bash
cd /path/to/multi-hid-proxy
sudo ./scripts/uninstall.sh
```

または手動で:

```bash
sudo systemctl stop keyboard-proxy.service
sudo systemctl stop multi-hid-gadget.service
sudo systemctl disable keyboard-proxy.service
sudo systemctl disable multi-hid-gadget.service

sudo rm -f /usr/local/bin/proxy_core.py
sudo rm -f /usr/local/bin/keyboard_proxy.py
sudo rm -f /usr/local/bin/mouse_proxy_rs
sudo rm -f /usr/local/bin/hid_keys.py
sudo rm -f /usr/local/bin/setup_hid_gadget.sh
sudo rm -f /etc/systemd/system/keyboard-proxy.service
sudo rm -f /etc/systemd/system/mouse-proxy@.service
sudo rm -f /etc/systemd/system/multi-hid-gadget.service
sudo rm -f /etc/udev/rules.d/99-mouse-proxy.rules
sudo rm -rf /etc/multi-hid-proxy

sudo systemctl daemon-reload
sudo udevadm control --reload-rules
```
