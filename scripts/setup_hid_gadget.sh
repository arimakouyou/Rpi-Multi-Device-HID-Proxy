#!/bin/bash
# =============================================================================
# USB HIDガジェット設定スクリプト
# =============================================================================
#
# このスクリプトは、Raspberry PiをUSB HIDデバイス（キーボード・マウス）として
# 動作させるためのガジェットモードを設定します。
#
# 機能:
#   - 複数キーボードエンドポイントの作成（/dev/hidg0, etc.）
#   - 複数マウスエンドポイントの作成（/dev/hidg1, /dev/hidg2, etc.）
#   - USB記述子の設定
#
# 前提条件:
#   - Raspberry Pi（USB OTG対応モデル: Pi Zero, Zero W, Zero 2W, Pi 4など）
#   - dwc2オーバーレイが有効（/boot/config.txt に dtoverlay=dwc2）
#   - libcomposite モジュールがロード済み
#   - ConfigFS がマウント済み（/sys/kernel/config）
#   - root権限
#
# 使用方法:
#   sudo ./setup_hid_gadget.sh
#
# 設定ファイル:
#   config.json から以下の情報を読み取ります:
#   - hid_paths.keyboard_outputs: キーボードエンドポイント数
#   - hid_paths.mouse_outputs: マウスエンドポイント数
#
# =============================================================================

# =============================================================================
# 設定ファイルの読み込み
# =============================================================================
# スクリプトの場所を基点に設定ファイルを検索
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")

# 設定ファイルの検索順序:
# 1. スクリプトと同じディレクトリ
# 2. /etc/multi-hid-proxy/（システムワイド設定）
if [ -f "$SCRIPT_DIR/config.json" ]; then
    CONFIG_FILE="$SCRIPT_DIR/config.json"
elif [ -f "/etc/multi-hid-proxy/config.json" ]; then
    CONFIG_FILE="/etc/multi-hid-proxy/config.json"
else
    echo "エラー: 設定ファイルが見つかりません。"
    echo "検索場所: $SCRIPT_DIR/config.json, /etc/multi-hid-proxy/config.json"
    exit 1
fi

# jqを使用してJSON設定からエンドポイント数を取得
NUM_KEYBOARDS=$(jq -r '.hid_paths.keyboard_outputs | length' "$CONFIG_FILE")
NUM_MICE=$(jq -r '.hid_paths.mouse_outputs | length' "$CONFIG_FILE")

# =============================================================================
# USBガジェットの基本設定
# =============================================================================
# USB Vendor ID: 0x1d6b = Linux Foundation
USB_VENDOR_ID="0x1d6b"
# USB Product ID: 0x013d = Multifunction Composite Gadget
USB_PRODUCT_ID="0x013d"
# シリアル番号（任意の識別子）
USB_SERIAL_NUMBER="0123456789"
# メーカー名
USB_MANUFACTURER="ARIMAKOUYOU"
# 製品名
USB_PRODUCT_NAME="Multi-HID-Proxy"

# =============================================================================
# スクリプト本体
# =============================================================================
# エラー発生時にスクリプトを終了
set -e

# =============================================================================
# 1. ガジェットディレクトリの作成とクリーンアップ
# =============================================================================
# ConfigFSのガジェットディレクトリ
GADGET_DIR="/sys/kernel/config/usb_gadget/g1"

if [ -d "$GADGET_DIR" ]; then
    echo "既存のガジェット設定をクリーンアップします..."
    
    # UDCからアンバインド（デバイスコントローラーから切り離す）
    if [ -f "$GADGET_DIR/UDC" ] && [ -n "$(cat "$GADGET_DIR/UDC")" ]; then
        echo "" > "$GADGET_DIR/UDC"
    fi
    
    # 設定を逆順で削除（依存関係があるため）
    # configsディレクトリ内の設定を削除
    for cfg_dir in "$GADGET_DIR"/configs/*; do
        if [ -d "$cfg_dir" ]; then
            # シンボリックリンク（関数へのリンク）を削除
            for func_link in "$cfg_dir"/*.*; do
                if [ -L "$func_link" ]; then
                    rm "$func_link"
                fi
            done
            # strings ディレクトリを削除
            if [ -d "$cfg_dir/strings/0x409" ]; then
                rmdir "$cfg_dir/strings/0x409"
            fi
            rmdir "$cfg_dir"
        fi
    done
    
    # functionsディレクトリ内の関数を削除
    for func_dir in "$GADGET_DIR"/functions/*; do
        if [ -d "$func_dir" ]; then
            rmdir "$func_dir"
        fi
    done
    
    # ガジェットのstringsディレクトリを削除
    if [ -d "$GADGET_DIR/strings/0x409" ]; then
        rmdir "$GADGET_DIR/strings/0x409"
    fi
    
    # ガジェットディレクトリ自体を削除
    rmdir "$GADGET_DIR"
fi

echo "新しいガジェットを作成します: $GADGET_DIR"
mkdir -p "$GADGET_DIR"

# =============================================================================
# 2. USB基本情報の書き込み
# =============================================================================
# USBデバイス記述子の設定
echo "$USB_VENDOR_ID" > "$GADGET_DIR/idVendor"
echo "$USB_PRODUCT_ID" > "$GADGET_DIR/idProduct"
echo "0x0200" > "$GADGET_DIR/bcdUSB"  # USB 2.0 準拠

# USB文字列記述子（英語）
mkdir -p "$GADGET_DIR/strings/0x409"  # 0x409 = 英語（米国）
echo "$USB_SERIAL_NUMBER" > "$GADGET_DIR/strings/0x409/serialnumber"
echo "$USB_MANUFACTURER" > "$GADGET_DIR/strings/0x409/manufacturer"
echo "$USB_PRODUCT_NAME" > "$GADGET_DIR/strings/0x409/product"

# =============================================================================
# 3. HID関数の設定
# =============================================================================

# -----------------------------------------------------------------------------
# キーボードHID関数の作成
# -----------------------------------------------------------------------------
for i in $(seq 0 $(($NUM_KEYBOARDS - 1))); do
    FUNC_DIR="$GADGET_DIR/functions/hid.usb$i"
    echo "キーボードHID関数を作成中: hid.usb$i"
    mkdir -p "$FUNC_DIR"
    
    # HIDプロトコル設定
    echo 1 > "$FUNC_DIR/protocol"    # 1 = キーボード
    echo 1 > "$FUNC_DIR/subclass"    # 1 = ブートインターフェース（BIOSでも使用可能）
    echo 8 > "$FUNC_DIR/report_length"  # レポートサイズ: 8バイト
    
    # キーボードHIDレポート記述子
    # USB HID仕様に基づく標準的なキーボード記述子
    # 
    # 構造:
    # - Usage Page (Generic Desktop): 0x05 0x01
    # - Usage (Keyboard): 0x09 0x06
    # - Collection (Application): 0xa1 0x01
    #   - モディファイアキー（8ビット）
    #   - 予約バイト（1バイト）
    #   - LEDインジケータ（5ビット）
    #   - キーコード配列（6バイト）
    # - End Collection: 0xc0
    echo -ne \\x05\\x01\\x09\\x06\\xa1\\x01\\x05\\x07\\x19\\xe0\\x29\\xe7\\x15\\x00\\x25\\x01\\x75\\x01\\x95\\x08\\x81\\x02\\x95\\x01\\x75\\x08\\x81\\x03\\x95\\x05\\x75\\x01\\x05\\x08\\x19\\x01\\x29\\x05\\x91\\x02\\x95\\x01\\x75\\x03\\x91\\x03\\x95\\x06\\x75\\x08\\x15\\x00\\x25\\xff\\x05\\x07\\x19\\x00\\x29\\xff\\x81\\x00\\xc0 > "$FUNC_DIR/report_desc"
done

# -----------------------------------------------------------------------------
# マウスHID関数の作成
# -----------------------------------------------------------------------------
for i in $(seq 0 $(($NUM_MICE - 1))); do
    # マウスのインデックスはキーボードの後から始まる
    IDX=$(($NUM_KEYBOARDS + $i))
    FUNC_DIR="$GADGET_DIR/functions/hid.usb$IDX"
    echo "マウスHID関数を作成中: hid.usb$IDX"
    mkdir -p "$FUNC_DIR"
    
    # HIDプロトコル設定
    echo 2 > "$FUNC_DIR/protocol"    # 2 = マウス
    echo 0 > "$FUNC_DIR/subclass"    # 0 = ブートインターフェースなし
    echo 7 > "$FUNC_DIR/report_length"  # レポートサイズ: 7バイト
    
    # マウスHIDレポート記述子
    # 5ボタンマウス + 16ビット移動量 + 16ビットホイール
    #
    # 構造:
    # - Usage Page (Generic Desktop): 0x05 0x01
    # - Usage (Mouse): 0x09 0x02
    # - Collection (Application): 0xa1 0x01
    #   - Usage (Pointer): 0x09 0x01
    #   - Collection (Physical): 0xa1 0x00
    #     - ボタン（5ビット）+ パディング（3ビット）
    #     - X, Y, Wheel（各16ビット符号付き整数）
    #   - End Collection: 0xc0
    # - End Collection: 0xc0
    echo -ne \\x05\\x01\\x09\\x02\\xa1\\x01\\x09\\x01\\xa1\\x00\\x05\\x09\\x19\\x01\\x29\\x05\\x15\\x00\\x25\\x01\\x95\\x05\\x75\\x01\\x81\\x02\\x95\\x01\\x75\\x03\\x81\\x03\\x05\\x01\\x09\\x30\\x09\\x31\\x09\\x38\\x16\\x01\\x80\\x26\\xff\\x7f\\x95\\x03\\x75\\x10\\x81\\x06\\xc0\\xc0 > "$FUNC_DIR/report_desc"
done

# =============================================================================
# 4. 設定の作成と関数のリンク
# =============================================================================
CONFIG_DIR="$GADGET_DIR/configs/c.1"
echo "設定ディレクトリを作成中: $CONFIG_DIR"

mkdir -p "$CONFIG_DIR"
mkdir -p "$CONFIG_DIR/strings/0x409"

# 設定の説明文字列
echo "Composite HID Gadget" > "$CONFIG_DIR/strings/0x409/configuration"
# 最大消費電力（mA）
echo 250 > "$CONFIG_DIR/MaxPower"

# 作成したHID関数をコンフィグレーションにシンボリックリンク
# これによりUSBホストに各HIDデバイスが公開される
for i in $(seq 0 $(($NUM_KEYBOARDS + $NUM_MICE - 1))); do
    ln -s "$GADGET_DIR/functions/hid.usb$i" "$CONFIG_DIR/"
done

# =============================================================================
# 5. UDC（USB Device Controller）へのバインド
# =============================================================================
# 利用可能なUSBデバイスコントローラーを検索
if [ -d "/sys/class/udc" ] && [ -n "$(ls -A /sys/class/udc)" ]; then
    # 最初に見つかったUDCを使用
    UDC=$(ls /sys/class/udc | head -n1)
    echo "UDC $UDC にガジェットをバインドします"
    
    # ガジェットをUDCにバインド（これによりUSBデバイスが有効化される）
    echo "$UDC" > "$GADGET_DIR/UDC"
    
    echo "USB HIDガジェットの設定が完了しました。"
    echo "  - キーボード: $NUM_KEYBOARDS 台"
    echo "  - マウス: $NUM_MICE 台"
else
    echo "警告: UDCが見つかりません。ガジェットは有効化されませんでした。"
fi

exit 0
