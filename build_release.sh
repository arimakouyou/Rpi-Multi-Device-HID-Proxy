#!/bin/bash
set -e

# プロジェクトルートディレクトリ (スクリプトのある場所)
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="${PROJECT_ROOT}/dist"
ARCHIVE_NAME="multi-hid-proxy-release.tar.gz"

# 引数の解析
TARGET_ARCH="aarch64" # デフォルトでRaspberry Pi Zero 2W用 (aarch64) に設定
while [[ $# -gt 0 ]]; do
    case $1 in
        --target)
            TARGET_ARCH="$2"
            shift 2
            ;;
        *)
            echo "不明なオプション: $1"
            exit 1
            ;;
    esac
done

echo "=== Multi HID Proxy ビルドスクリプト開始 ==="

# 1. Rustプロジェクトのビルド
echo "[1/4] Rustバイナリ (mouse_proxy_rs) をビルドしています..."
cd "${PROJECT_ROOT}/rust/mouse_proxy_rs"

# cargoコマンドがない場合、パスを通してみる
if ! command -v cargo &> /dev/null; then
    if [ -f "$HOME/.cargo/env" ]; then
        source "$HOME/.cargo/env"
    fi
fi

if ! command -v cargo &> /dev/null; then
    echo "エラー: cargo コマンドが見つかりません。Rust環境をインストールしてください。"
    exit 1
fi

BUILD_CMD="cargo build --release"

if [ -n "$TARGET_ARCH" ] && [ "$TARGET_ARCH" != "native" ]; then
    echo "ターゲットアーキテクチャ: $TARGET_ARCH"
    if [[ "$TARGET_ARCH" == "aarch64" || "$TARGET_ARCH" == "aarch64-unknown-linux-gnu" ]]; then
        TARGET_TRIPLE="aarch64-unknown-linux-gnu"
        LINKER="aarch64-linux-gnu-gcc"

        # リンカーのチェック
        if ! command -v "$LINKER" &> /dev/null; then
            echo "エラー: リンカー '$LINKER' が見つかりません。"
            echo "インストールしてください: sudo apt install gcc-aarch64-linux-gnu"
            exit 1
        fi

        # ターゲットの追加チェック (簡易)
        if ! rustup target list --installed | grep -q "$TARGET_TRIPLE"; then
             echo "警告: Rustターゲット '$TARGET_TRIPLE' がインストールされていない可能性があります。"
             echo "実行してみてください: rustup target add $TARGET_TRIPLE"
             # 続行する (すでにあるかもしれないし、rustupがない環境かもしれないので)
        fi

        # 環境変数でリンカーを指定してビルド
        export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER="$LINKER"
        BUILD_CMD="cargo build --release --target $TARGET_TRIPLE"
        
        # バイナリパスの更新 (ターゲットディレクトリが変わるため)
        BINARY_PATH="${PROJECT_ROOT}/rust/mouse_proxy_rs/target/$TARGET_TRIPLE/release/mouse_proxy_rs"
    else
        echo "エラー: サポートされていないアーキテクチャです: $TARGET_ARCH"
        exit 1
    fi
else
    # ネイティブビルド
    echo "ターゲットアーキテクチャ: native (host)"
    BINARY_PATH="${PROJECT_ROOT}/rust/mouse_proxy_rs/target/release/mouse_proxy_rs"
fi

echo "実行コマンド: $BUILD_CMD"
eval "$BUILD_CMD"

if [ ! -f "$BINARY_PATH" ]; then
    echo "エラー: バイナリのビルドに失敗しました ($BINARY_PATH が見つかりません)"
    exit 1
fi

# 2. 配布用ディレクトリの作成とクリーンアップ
echo "[2/4] 配布用ディレクトリ ($DIST_DIR) を準備しています..."
rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"

# 3. ファイルのコピー
echo "[3/4] 必要なファイルをコピーしています..."

# バイナリ
cp "$BINARY_PATH" "$DIST_DIR/"

# スクリプトと設定ファイル
# install.sh はルートにあるものをコピー
cp "${PROJECT_ROOT}/install.sh" "$DIST_DIR/"
cp "${PROJECT_ROOT}/config.json.sample" "$DIST_DIR/"

# Pythonスクリプト (Keyboard Proxy等はまだPythonなので)
cp "${PROJECT_ROOT}/proxy_core.py" "$DIST_DIR/"
cp "${PROJECT_ROOT}/keyboard_proxy.py" "$DIST_DIR/"
cp "${PROJECT_ROOT}/hid_keys.py" "$DIST_DIR/"
cp "${PROJECT_ROOT}/setup_hid_gadget.sh" "$DIST_DIR/"

# systemd サービスファイル
cp "${PROJECT_ROOT}/keyboard-proxy.service" "$DIST_DIR/"
cp "${PROJECT_ROOT}/mouse-proxy@.service" "$DIST_DIR/"
cp "${PROJECT_ROOT}/multi-hid-gadget.service" "$DIST_DIR/"

# udev ルール
cp "${PROJECT_ROOT}/99-mouse-proxy.rules" "$DIST_DIR/"

# 実行権限の付与 (念のため)
chmod +x "$DIST_DIR/install.sh"
chmod +x "$DIST_DIR/mouse_proxy_rs"
chmod +x "$DIST_DIR"/*.py
chmod +x "$DIST_DIR"/*.sh

# 4. アーカイブの作成
echo "[4/4] アーカイブ ($ARCHIVE_NAME) を作成しています..."
cd "${PROJECT_ROOT}"
# dist ディレクトリの中身をアーカイブする (展開時に散らばらないようにフォルダを含めるか、カレントに展開するか)
# ここでは dist の中身をトップレベルとしてアーカイブします。
# ユーザーが mkdir して展開することを想定、または install.sh で配慮。
# 一般的にはフォルダ一つ掘ったほうが親切ですが、install.sh がルートにあると便利なので
# そのままアーカイブします。

tar -czvf "$ARCHIVE_NAME" -C "$DIST_DIR" .

echo "=== ビルド完了 ==="
echo "生成されたアーカイブ: ${PROJECT_ROOT}/${ARCHIVE_NAME}"
