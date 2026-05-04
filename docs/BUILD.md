# ビルドガイド

このドキュメントでは、ソースコードからプロジェクトをビルドする方法を説明します。

## 必要なツール

### Rust環境

マウスプロキシ（`mouse_proxy_rs`）のビルドにはRust環境が必要です。

```bash
# Rustのインストール
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env
```

### クロスコンパイル環境（オプション）

開発マシンからRaspberry Pi用にビルドする場合:

```bash
# aarch64ターゲットの追加
rustup target add aarch64-unknown-linux-gnu

# クロスコンパイラのインストール（Ubuntu/Debian）
sudo apt install gcc-aarch64-linux-gnu
```

### Python依存関係

```bash
sudo apt install python3-evdev python3-gpiozero
```

オプション（Keybow Mini の APA102 LED を使用する場合）:

```bash
sudo apt install python3-spidev
# /boot/firmware/config.txt に dtparam=spi=on を追記して再起動も必要
```

## ビルド方法

### 自動ビルド（推奨）

`build_release.sh` スクリプトを使用してリリースアーカイブを作成:

```bash
# Raspberry Pi Zero 2W (aarch64) 向けにビルド
./scripts/build_release.sh

# ネイティブビルド（開発マシン上でテスト用）
./scripts/build_release.sh --target native
```

ビルド完了後、`multi-hid-proxy-release.tar.gz` が生成されます。

### 手動ビルド

#### 1. マウスプロキシのビルド

```bash
cd rust/mouse_proxy_rs

# ネイティブビルド
cargo build --release

# クロスコンパイル（aarch64）
CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER=aarch64-linux-gnu-gcc \
  cargo build --release --target aarch64-unknown-linux-gnu
```

バイナリは以下に生成されます:

- ネイティブ: `target/release/mouse_proxy_rs`
- クロスコンパイル: `target/aarch64-unknown-linux-gnu/release/mouse_proxy_rs`

#### 2. Pythonスクリプト

Pythonスクリプトはビルド不要です。そのまま使用できます。

## リリースアーカイブの内容

`build_release.sh` で生成されるアーカイブには以下が含まれます:

```
multi-hid-proxy-release.tar.gz
├── install.sh
├── config.json.sample
├── mouse_proxy_rs
├── proxy_core.py
├── keyboard_proxy.py
├── hid_keys.py
├── setup_hid_gadget.sh
├── keyboard-proxy.service
├── mouse-proxy@.service
├── multi-hid-gadget.service
└── 99-mouse-proxy.rules
```

## 開発環境での実行

### マウスプロキシの単体テスト

```bash
cd rust/mouse_proxy_rs
cargo run -- /dev/input/eventX /dev/hidgY
```

### キーボードプロキシの単体テスト

```bash
sudo python3 src/keyboard_proxy.py
```

## トラブルシューティング

### クロスコンパイルエラー

リンカーが見つからない場合:

```bash
# リンカーのインストール
sudo apt install gcc-aarch64-linux-gnu

# 環境変数の設定
export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER=aarch64-linux-gnu-gcc
```

### Rustターゲットがない

```bash
rustup target add aarch64-unknown-linux-gnu
```

### Python依存関係エラー

```bash
# evdevのインストール
sudo apt install python3-evdev

# gpiozeroのインストール
sudo apt install python3-gpiozero
```
