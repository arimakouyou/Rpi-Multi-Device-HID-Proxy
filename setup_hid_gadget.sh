#!/bin/bash
#
# このスクリプトは、複数のキーボードとマウスを中継するUSB HIDプロキシデバイスを設定します。
# 1つのキーボードと2つのマウス用のHIDエンドポイントを作成します。
#
# 実行するにはroot権限が必要です。
# (e.g., sudo ./setup_hid_gadget.sh)
#

# --- 設定 ---
# config.jsonから設定を読み込む
# スクリプトの場所に加え、/etc/multi-hid-proxy/ も検索
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
if [ -f "$SCRIPT_DIR/config.json" ]; then
    CONFIG_FILE="$SCRIPT_DIR/config.json"
elif [ -f "/etc/multi-hid-proxy/config.json" ]; then
    CONFIG_FILE="/etc/multi-hid-proxy/config.json"
else
    echo "エラー: 設定ファイルが見つかりません。"
    echo "検索場所: $SCRIPT_DIR/config.json, /etc/multi-hid-proxy/config.json"
    exit 1
fi

# jqを使ってJSONから値を取得
NUM_KEYBOARDS=$(jq -r '.hid_paths.keyboard_outputs | length' "$CONFIG_FILE")
NUM_MICE=$(jq -r '.hid_paths.mouse_outputs | length' "$CONFIG_FILE")

# USBガジェットの基本設定
USB_VENDOR_ID="0x1d6b"  # Linux Foundation
USB_PRODUCT_ID="0x013d" # Multifunction Composite Gadget
USB_SERIAL_NUMBER="0123456789"
USB_MANUFACTURER="ARIMAKOUYOU"
USB_PRODUCT_NAME="Multi-HID-Proxy"

# --- スクリプト本体 ---
set -e # エラーが発生したらスクリプトを終了

# 1. ガジェットディレクトリの作成
# ---------------------------------
GADGET_DIR="/sys/kernel/config/usb_gadget/g1"
if [ -d "$GADGET_DIR" ]; then
    echo "既存のガジェット設定をクリーンアップします..."
    # 既存のガジェットを無効化
    if [ -f "$GADGET_DIR/UDC" ] && [ -n "$(cat "$GADGET_DIR/UDC")" ]; then
        echo "" > "$GADGET_DIR/UDC"
    fi
    # 既存の設定を削除（逆順で）
    for cfg_dir in "$GADGET_DIR"/configs/*; do
        if [ -d "$cfg_dir" ]; then
            for func_link in "$cfg_dir"/*.*; do
                if [ -L "$func_link" ]; then
                    rm "$func_link"
                fi
            done
            # stringsディレクトリを削除
            if [ -d "$cfg_dir/strings/0x409" ]; then
                rmdir "$cfg_dir/strings/0x409"
            fi
            rmdir "$cfg_dir"
        fi
    done
    for func_dir in "$GADGET_DIR"/functions/*; do
        if [ -d "$func_dir" ]; then
            rmdir "$func_dir"
        fi
    done
    # stringsディレクトリを削除
    if [ -d "$GADGET_DIR/strings/0x409" ]; then
        rmdir "$GADGET_DIR/strings/0x409"
    fi
    rmdir "$GADGET_DIR"
fi
echo "新しいガジェットを作成します: $GADGET_DIR"
mkdir -p "$GADGET_DIR"

# 2. USB基本情報の書き込み
# ---------------------------------
echo "$USB_VENDOR_ID" > "$GADGET_DIR/idVendor"
echo "$USB_PRODUCT_ID" > "$GADGET_DIR/idProduct"
echo "0x0200" > "$GADGET_DIR/bcdUSB" # USB 2.0
mkdir -p "$GADGET_DIR/strings/0x409"
echo "$USB_SERIAL_NUMBER" > "$GADGET_DIR/strings/0x409/serialnumber"
echo "$USB_MANUFACTURER" > "$GADGET_DIR/strings/0x409/manufacturer"
echo "$USB_PRODUCT_NAME" > "$GADGET_DIR/strings/0x409/product"

# 3. HID関数の設定
# ---------------------------------
# キーボード用
for i in $(seq 0 $(($NUM_KEYBOARDS - 1))); do
    FUNC_DIR="$GADGET_DIR/functions/hid.usb$i"
    echo "キーボードHID関数を作成中: hid.usb$i"
    mkdir -p "$FUNC_DIR"
    echo 1 > "$FUNC_DIR/protocol"    # Keyboard
    echo 1 > "$FUNC_DIR/subclass"    # Boot Interface
    echo 8 > "$FUNC_DIR/report_length"
    # キーボードのレポートディスクリプタ
    echo -ne \\x05\\x01\\x09\\x06\\xa1\\x01\\x05\\x07\\x19\\xe0\\x29\\xe7\\x15\\x00\\x25\\x01\\x75\\x01\\x95\\x08\\x81\\x02\\x95\\x01\\x75\\x08\\x81\\x03\\x95\\x05\\x75\\x01\\x05\\x08\\x19\\x01\\x29\\x05\\x91\\x02\\x95\\x01\\x75\\x03\\x91\\x03\\x95\\x06\\x75\\x08\\x15\\x00\\x25\\xff\\x05\\x07\\x19\\x00\\x29\\xff\\x81\\x00\\xc0 > "$FUNC_DIR/report_desc"
done

# マウス用
for i in $(seq 0 $(($NUM_MICE - 1))); do
    IDX=$(($NUM_KEYBOARDS + $i))
    FUNC_DIR="$GADGET_DIR/functions/hid.usb$IDX"
    echo "マウスHID関数を作成中: hid.usb$IDX"
    mkdir -p "$FUNC_DIR"
    echo 2 > "$FUNC_DIR/protocol"    # Mouse
    echo 0 > "$FUNC_DIR/subclass"
    echo 8 > "$FUNC_DIR/report_length"
    # マウスのレポートディスクリプタ
    echo -ne \\x05\\x01\\x09\\x02\\xa1\\x01\\x09\\x01\\xa1\\x00\\x05\\x09\\x19\\x01\\x29\\x05\\x15\\x00\\x25\\x01\\x95\\x05\\x75\\x01\\x81\\x02\\x05\\x01\\x09\\x30\\x09\\x31\\x09\\x38\\x15\\x81\\x25\\x7f\\x75\\x10\\x95\\x03\\x81\\x06\\xc0\\xc0 > "$FUNC_DIR/report_desc"
done

# 4. 設定の作成と関数のリンク
# ---------------------------------
CONFIG_DIR="$GADGET_DIR/configs/c.1"
echo "設定ディレクトリを作成中: $CONFIG_DIR"
mkdir -p "$CONFIG_DIR"
mkdir -p "$CONFIG_DIR/strings/0x409"
echo "Composite HID Gadget" > "$CONFIG_DIR/strings/0x409/configuration"
echo 250 > "$CONFIG_DIR/MaxPower"

# 作成したHID関数をコンフィグレーションにリンク
for i in $(seq 0 $(($NUM_KEYBOARDS + $NUM_MICE - 1))); do
    ln -s "$GADGET_DIR/functions/hid.usb$i" "$CONFIG_DIR/"
done

# 5. UDC（USB Device Controller）へのバインド
# ---------------------------------
# 利用可能なUDCを検索してバインド
if [ -d "/sys/class/udc" ] && [ -n "$(ls -A /sys/class/udc)" ]; then
    UDC=$(ls /sys/class/udc | head -n1)
    echo "UDC $UDC にガジェットをバインドします"
    echo "$UDC" > "$GADGET_DIR/UDC"
    echo "USB HIDガジェットの設定が完了しました。"
    echo "  - キーボード: $NUM_KEYBOARDS 台"
    echo "  - マウス: $NUM_MICE 台"
else
    echo "警告: UDCが見つかりません。ガジェットは有効化されませんでした。"
fi

exit 0

