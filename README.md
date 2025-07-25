# Multi-Device HID Proxy

## 1. 概要

このプロジェクトは、Raspberry PiなどのLinuxデバイスを、複数のBluetoothキーボードやマウスを中継するUSBプロキシデバイスとして機能させるためのソフトウェア一式です。viggofalster/kiriをベースに、設定の外部化、日本語配列対応の強化、複数デバイス管理の安定性向上など、多くの改良を加えています。

これにより、複数の無線デバイスを、あたかも単一の有線USBデバイスであるかのようにホストPCに接続できます。実行中のデバイスの動的な接続・切断にも対応しています。

## 2. 主な機能

*   **複数デバイス対応**: 複数のキーボードとマウスを同時に接続し、プロキシとして動作させます。
*   **外部設定ファイル**: `config.json`により、ソースコードを編集することなく動作をカスタマイズできます。
*   **動的認識**: プログラムの実行中にBluetoothデバイスを接続・切断しても、自動で認識・解放します。
*   **高度なキーリマップ**: US配列キーボードの日本語配列化や、特殊キー（無変換、変換など）のマッピングが可能です。
*   **Systemd連携**: システム起動時に、USBガジェットの設定とプロキシプログラムが自動的に起動します。
*   **GPIO対応**: Raspberry PiのGPIOピンに接続したボタンに、カスタムの動作を割り当てることができます。

## 3. ファイル構成

| ファイル名 | 説明 |
| :--- | :--- |
| `multi_device_proxy.py` | メインのプロキシプログラム。デバイスを監視し、入力を中継します。 |
| `setup_hid_gadget.sh` | USB HIDガジェット（キーボードとマウス）を作成・設定するスクリプト。 |
| `hid_keys.py` | HIDキーコードのマップファイル。 |
| `config.json` | 動作設定を定義するJSONファイル。 |
| `config.json.sample` | `config.json`のサンプルファイル。 |
| `CONFIG.md` | `config.json`の詳細な設定方法を記述したドキュメント。 |
| `multi-hid-gadget.service` | `setup_hid_gadget.sh`をシステム起動時に実行するSystemdサービス。 |
| `multi-hid-proxy.service` | `multi_device_proxy.py`をシステムサービスとして実行する定義ファイル。 |
| `install.sh` | ファイルを適切な場所にコピーし、サービスを有効化するスクリプト。 |
| `uninstall.sh` | インストールされたファイルをシステムから削除するスクリプト。 |
| `README.md` | このファイルです。 |

## 4. 前提条件

*   USB On-The-Go (OTG) をサポートするLinuxデバイス（例: Raspberry Pi Zero, Raspberry Pi 4など）
*   Python 3
*   必要なPythonライブラリ:
    *   `evdev`: `sudo apt-get install python3-evdev` などでインストール
    *   `gpiozero` (任意、GPIO機能利用時): `sudo apt-get install python3-gpiozero` などでインストール

## 5. インストール手順

1.  このパッケージに含まれるすべてのファイルを、デバイスの同じディレクトリに配置します。
2.  `config.json.sample` を `config.json` にコピーし、内容を編集して設定を行います。（詳細は「6. 設定」を参照）
    ```bash
    cp config.json.sample config.json
    nano config.json
    ```
3.  ターミナルで以下のコマンドを実行し、インストールスクリプトに実行権限を与えます。
    ```bash
    chmod +x install.sh uninstall.sh setup_hid_gadget.sh
    ```
4.  以下のコマンドでインストールを実行します。
    ```bash
    sudo ./install.sh
    ```
5.  インストール完了後、システムを再起動します。
    ```bash
    sudo reboot
    ```
    再起動後、サービスが自動的に開始され、プロキシが有効になります。

## 6. 設定

本プログラムの設定はすべて `config.json` ファイルで行います。詳細な設定方法は `CONFIG.md` を参照してください。

### 基本的な設定手順

1.  `config.json.sample` を `config.json` にコピーします。
2.  `config.json` を開き、お使いの環境に合わせて値を変更します。

### 主な設定項目

*   **デバイス名の設定**:
    `config.json`内の`keyboard_patterns`と`mouse_patterns`に、お使いのデバイス名に一致する正規表現パターンを配列形式で追加します。
    ```json
    "keyboard_patterns": [
        "HHKB-Studio_Keyboard",
        "HHKB-Hybrid.*",
        "Logitech.*"
    ],
    "mouse_patterns": [
        "HHKB-Studio_Mouse"
    ]
    ```
    デバイス名は[付録](#付録-デバイス名の確認方法)の方法で確認できます。

*   **キーリマップの設定**:
    `remap_rules`セクションで、キーの変換ルールを定義します。例えば、US配列の`KEY_GRAVE`（`~`キー）を日本語配列の`KEY_ZENKAKUHANKAKU`（半角/全角キー）に割り当てるには、以下のように設定します。
    ```json
    "remap_rules": {
        "KEY_GRAVE": "KEY_ZENKAKUHANKAKU"
    }
    ```

*   **接続数の変更**:
    同時に接続するキーボードとマウスの最大数を変更するには、`setup_hid_gadget.sh` スクリプト内の `NUM_KEYBOARDS` と `NUM_MICE` の値を変更してください。

## 7. アンインストール

システムからこのプログラムを削除するには、以下のコマンドを実行します。
```bash
sudo ./uninstall.sh
```

---

### 付録: デバイス名の確認方法

ターミナルで以下のコマンドを実行すると、現在システムに認識されている入力デバイスの一覧が表示されます。この中から、お使いのデバイスの正確な名前を確認できます。
```bash
python3 -c "import evdev; [print(f'Path: {p}, Name: \"{evdev.InputDevice(p).name}\"') for p in evdev.list_devices()]"
```

