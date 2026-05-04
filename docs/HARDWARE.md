# ハードウェア配線ガイド

本ドキュメントは Rpi-Multi-Device-HID-Proxy で使用するハードウェアの選定と物理配線をまとめたものです。設定値の変更方法は [CONFIGURATION.md](CONFIGURATION.md)、ソフトウェアのインストールは [INSTALL.md](INSTALL.md) を参照してください。

## 1. 必要な部品（BOM）

本プロジェクトは **Pimoroni Keybow Mini** (3 キー + APA102 RGB LED 3 個の小型キーパッド) を物理ターゲットとして設計されています。

| 部品 | 数量 | 補足 |
|---|---|---|
| Raspberry Pi Zero 2W | 1 | OTG 対応モデルなら Pi 4 / Pi 5 / Pi Zero / Pi Zero W でも可 |
| **Pimoroni Keybow Mini キット** | 1 | 3 キー + 3 RGB LED (APA102)。Pi Zero / Zero 2W に対応する HAT 形状 |
| microSD カード | 1 | 8 GB 以上、Class 10 以上推奨 |
| USB OTG ケーブル | 1 | **データ通信対応**のものを選ぶこと（充電専用ケーブルは不可） |
| 電源 | 1 | Pi の給電用（OTG ポートを USB ガジェットとして使う場合は別途給電が必要なケースあり） |

Keybow Mini はキーキャップ内部に APA102C LED を内蔵しており、SPI 経由で各キーの色を個別制御できます。Pi Zero 2W に直接装着する形で 3 つのスイッチも GPIO に配線済みです。

### 上流入力デバイス（動作確認済み）
- **HHKB Studio / Hybrid + Logitech マウス**: USB 経由で Pi に接続し、本プロキシが集約してホスト PC に送信。`udev/99-mouse-proxy.rules` に対応ルールあり。

### Keybow Mini を使わない場合の代替
ボタンだけを別途タクトスイッチで作る場合は GPIO 6 / 22 / 17 を使ってください（§3 参照）。LED は APA102 互換ストリップを SPI に接続すれば再利用可能です。WS2812B (NeoPixel) を使いたい場合は本プロジェクトのコード/ライブラリ選定を変更する必要があります。

## 2. Raspberry Pi の USB OTG 設定

ホスト PC に対して Pi を「USB デバイス」として見せるため、USB OTG (On-The-Go) を有効化します。

`/boot/firmware/config.txt` に以下を追記:

```
dtoverlay=dwc2
```

`/boot/firmware/cmdline.txt` の `rootwait` の後に半角スペース区切りで以下を追加:

```
modules-load=dwc2,libcomposite
```

> Pi 4 / Pi 5 では USB-C 給電ポートを OTG として使います。Pi Zero 2W では中央の microUSB ポート（電源側ではないほう）を OTG として使います。**ホスト PC へは OTG ポートを介して接続**してください。

詳細手順とインストール時のチェックは [INSTALL.md](INSTALL.md#事前準備) を参照してください。

## 3. GPIO ボタン配線

ボタン番号、GPIO 番号、物理ピン番号、機能の対応は以下のとおりです（実装ソース: `src/keyboard_proxy.py:531-543`）。

| ボタン | GPIO 番号 | 物理ピン番号 | 短押し動作 | 長押し動作 |
|---|---|---|---|---|
| Btn1 | **GPIO 6** | 31 | Alt+A 送信 | リマップ機能の有効/無効トグル |
| Btn2 | **GPIO 22** | 15 | Alt+Y 送信 | （単独では未割当） |
| Btn3 | **GPIO 17** | 11 | Space 送信 | （単独では未割当） |
| Btn1+Btn2 | — | — | — | メールアドレス自動入力 |
| Btn1+Btn3 | — | — | — | システムシャットダウン |

実装ソース: 短押し/長押しの分岐は `src/keyboard_proxy.py:653-740`。長押し判定時間と短押し時のチャタリング防止時間は `config.json` の `gpio_settings` で調整できます（[CONFIGURATION.md](CONFIGURATION.md#gpio_settings) 参照）。

### 配線

各ボタンは GPIO ピンと **GND** の間に挟むだけで動作します。

```
   タクトスイッチ
   ┌─────┐
   │     │
   │  ●──┼─── GPIO（例: 物理 31 = GPIO6）
   │     │
   │  ●──┼─── GND（例: 物理 9, 25, 39 など）
   │     │
   └─────┘
```

`gpiozero.Button` のデフォルトは `pull_up=True` なので、Pi 内部のプルアップ抵抗が有効になり、**外部抵抗は不要**です（実装: `src/keyboard_proxy.py:56-63`）。

### GND 共通

3 つのボタンと LED の GND は Pi の GND ピンに共通で繋いで構いません。Keybow Mini の HAT を使う場合は配線済み。

## 4. APA102 LED 配線 (Keybow Mini)

LED はリマップ機能の有効/無効をユーザーに視覚的に通知するために使います。実装は専用クラス `LedStatusManager` (`src/keyboard_proxy.py` 内) に分離されており、ライブラリ未導入や SPI 未有効など初期化失敗時もキーボードプロキシ本体には影響しません。

Keybow Mini は **APA102C 系の RGB LED** を 3 個搭載し、**SPI バス経由**で制御します（**WS2812B / NeoPixel ではありません**。歴史的経緯は [DEVELOPMENT.md](DEVELOPMENT.md) を参照）。

| 信号 | Pi 側 GPIO | 物理ピン番号 | Keybow Mini 側 |
|---|---|---|---|
| **データ (DI)** | **GPIO 10 (SPI0_MOSI)** | 19 | APA102 DI |
| **クロック (CI)** | **GPIO 11 (SPI0_SCLK)** | 23 | APA102 CI |
| **5V 電源 (VCC)** | 5V | 2 または 4 | APA102 VCC |
| **GND** | GND | 6 / 9 / 14 / 20 / 25 / 30 / 34 / 39 のいずれか | APA102 GND |

Keybow Mini の HAT を Pi に装着する場合、これらの配線は HAT 側で完結しています。手配線の場合は上の表どおりにジャンパで結線してください。

### 配線図 (手配線時の参考)

```
   Raspberry Pi (40-pin header)         APA102 LED ×3 (Keybow Mini 内蔵)
   ┌───────────────────┐                ┌──────┬──────┬──────┐
   │                   │                │ LED1 │ LED2 │ LED3 │
   │ pin 2  (5V)   ────┼─── VCC ───────▶│ VCC  │ VCC  │ VCC  │
   │ pin 19 (GPIO10) ──┼─── DI ────────▶│ DI   │      │      │
   │ pin 23 (GPIO11) ──┼─── CI ────────▶│ CI   │      │      │
   │                   │                │ DO ──┼─ DI  │      │
   │                   │                │ CO ──┼─ CI  │      │
   │                   │                │      │ DO ──┼─ DI  │
   │                   │                │      │ CO ──┼─ CI  │
   │ pin 6  (GND)  ────┼─── GND ───────▶│ GND  │ GND  │ GND  │
   └───────────────────┘                └──────┴──────┴──────┘
```

LED 数はデフォルト 3 個ですが、`config.json` の `led_settings.led_count` で変更可能です（[CONFIGURATION.md](CONFIGURATION.md#led_settings)）。

### SPI の有効化

APA102 を駆動するには Pi の SPI バスが有効化されている必要があります。

```bash
# /boot/firmware/config.txt に dtparam=spi=on を追記
sudo grep -q "^dtparam=spi=on" /boot/firmware/config.txt || \
  echo "dtparam=spi=on" | sudo tee -a /boot/firmware/config.txt
sudo reboot
# 起動後の確認
ls /dev/spidev0.*   # spidev0.0 / spidev0.1 が見えれば OK
```

`scripts/install.sh` を実行すれば自動で追記されます。

### LED の状態表示

| 状態 | 色（デフォルト） | 配列 |
|---|---|---|
| リマップ機能 **有効** | 緑 | `[0, 255, 0]` |
| リマップ機能 **無効** | 赤 | `[255, 0, 0]` |

色は `config.json` の `led_settings.colors` で変更できます。

### 5V 給電と信号レベル

APA102 は SPI 信号 (3.3V CMOS) を直接受け付けるため、WS2812B のような 5V レベルシフタは原則不要です。LED 本体には 5V 電源が必要なので Pi の 5V ピンから給電してください。LED 個数を増やす場合は別電源を検討します。

## 5. ピンマップ ASCII 図（40 ピンヘッダ）

Pi Zero 2W / Pi 3 / Pi 4 共通の 40 ピンヘッダにおける本プロジェクトでの使用ピン:

```
                       40-pin GPIO header (上から見た図)
                ┌──────────────────────────────────────┐
        3V3  1  │ ●  ●  │  2   5V         <-- LED VCC (5V)
       GPIO2 3  │ ●  ●  │  4   5V
       GPIO3 5  │ ●  ●  │  6   GND        <-- LED GND / Btn GND
       GPIO4 7  │ ●  ●  │  8   GPIO14
        GND  9  │ ●  ●  │  10  GPIO15
      GPIO17 11 │ ◉  ●  │  12  GPIO18     <-- Btn3=GPIO17
      GPIO27 13 │ ●  ●  │  14  GND
      GPIO22 15 │ ◉  ●  │  16  GPIO23     <-- Btn2=GPIO22
        3V3  17 │ ●  ●  │  18  GPIO24
      GPIO10 19 │ ◉  ●  │  20  GND        <-- LED DI = GPIO10 (SPI0_MOSI)
       GPIO9 21 │ ●  ●  │  22  GPIO25
      GPIO11 23 │ ◉  ●  │  24  GPIO8      <-- LED CI = GPIO11 (SPI0_SCLK)
        GND  25 │ ●  ●  │  26  GPIO7
       GPIO0 27 │ ●  ●  │  28  GPIO1
       GPIO5 29 │ ●  ●  │  30  GND
       GPIO6 31 │ ◉  ●  │  32  GPIO12     <-- Btn1=GPIO6
      GPIO13 33 │ ●  ●  │  34  GND
      GPIO19 35 │ ●  ●  │  36  GPIO16
      GPIO26 37 │ ●  ●  │  38  GPIO20
        GND  39 │ ●  ●  │  40  GPIO21
                └──────────────────────────────────────┘

   凡例:  ◉ = 本プロジェクトで使用するピン
         ●  = 未使用または GND/電源
```

## 6. 動作確認手順

ハードウェア組み立て後、ソフトウェアインストール前に以下で配線を検証できます。

### 6.1 ボタン

```bash
# Pi 上で
python3 - <<'PY'
from gpiozero import Button
from time import sleep
buttons = {1: Button(6), 2: Button(22), 3: Button(17)}
print("Press buttons (Ctrl+C to exit)...")
while True:
    for n, b in buttons.items():
        if b.is_pressed:
            print(f"Btn{n} pressed")
    sleep(0.05)
PY
```

3 つのボタンを押すと対応する番号がコンソールに出力されることを確認します。

### 6.2 APA102 LED (Keybow Mini)

```bash
# 前提: SPI 有効化済み (/dev/spidev0.0 が見える), python3-spidev インストール済み
# sudo apt install -y python3-spidev
sudo python3 - <<'PY'
import spidev, time
spi = spidev.SpiDev()
spi.open(0, 0)               # /dev/spidev0.0
spi.max_speed_hz = 4000000
NUM = 3
def show(r, g, b, br=31):
    data = [0x00] * 4                          # start frame
    for _ in range(NUM):
        data += [0xE0 | (br & 0x1F), b, g, r]  # APA102 frame: hdr, B, G, R
    data += [0xFF] * ((NUM + 15) // 16)        # end frame
    spi.xfer2(data)
for rgb in [(255,0,0), (0,255,0), (0,0,255), (0,0,0)]:
    print("show", rgb); show(*rgb); time.sleep(1)
spi.close()
PY
```

赤 → 緑 → 青 → 消灯の順で 3 つの LED が点灯することを確認します。

### 6.2.1 LED が点灯しないときのチェック順序

実機に組み込んだ後、リマップ状態を切り替えても LED が変化しない／そもそも点灯しない場合は、以下の順で切り分けてください。

1. **SPI が有効になっているか**
   ```bash
   ls /dev/spidev0.*
   ```
   `spidev0.0` / `spidev0.1` が表示されない場合は `/boot/firmware/config.txt` に `dtparam=spi=on` を追記して再起動してください (`scripts/install.sh` でも自動追記)。

2. **journalctl で初期化ログを確認**
   ```bash
   sudo journalctl -u keyboard-proxy.service -n 100 | grep -i led
   ```
   - `LED hardware initialized: 3 APA102 LEDs on spidev0.0 ...` が出ているか
   - `LED disabled by config.` → `config.json` の `led_settings.enabled` が `false` になっている
   - `LED enabled in config but python3-spidev not installed` → `sudo apt install python3-spidev`
   - `LED init failed: ... PermissionError` → root 権限で実行されているか / `/dev/spidev*` の権限を確認

3. **起動セルフテスト (赤→緑→青) が見えるか**
   起動直後 (約 1.2 秒) に 3 色のフラッシュが見えれば、SPI / 配線 / 電源は健全。見えない場合は §6.2 の単体スクリプトで spidev レベルの動作を確認する。

4. **セルフテストは見えるが Btn1 で色が変わらない**
   LED 系は健全。`REMAP_ENABLED` トグル側 (`src/keyboard_proxy.py` 内 `held1`) や Btn1 の GPIO 結線を疑う。`journalctl` に `Btn 1 Held: Remap Enabled/Disabled` が出ているかが見分けポイント。

5. **`logging.level` が `ERROR` になっていないか**
   `INFO` 以上でないと LED 関連のログは流れません (`config.json` の `logging.level`)。

セルフテストをスキップしたい場合は `config.json` の `led_settings.boot_self_test` を `false` にしてください。

### 6.3 USB OTG

ホスト PC に OTG ケーブルで接続した状態で:

```bash
# Pi 上で
lsmod | grep -E 'dwc2|libcomposite'
ls -la /sys/class/udc/   # UDC ドライバが見えるはず
```

何も表示されない場合は `/boot/firmware/config.txt` と `/boot/firmware/cmdline.txt` の設定を見直してください。

## 7. 既知の制限と代替案

### 7.1 GPIO ピン番号がハードコード

ボタン (`GPIO 6 / 22 / 17`) は `src/keyboard_proxy.py` の `KeyBowManager.__init__` でハードコードされています。LED の SPI バス／デバイスは `config.json` の `led_settings.spi_bus` / `spi_device` で上書き可能ですが、ボタン側はソース改変が必要です。

別の GPIO に変えたい場合は `KeyBowManager.__init__` の `Button(N)` を編集してください。

### 7.2 SPI バスを他用途と共用する場合

APA102 LED は `/dev/spidev0.0` を占有します（書き込みのみ・読み出しなし）。他の SPI デバイス (例: SPI 接続のセンサ) と同居させたい場合は、`led_settings.spi_device` を `1` (= `/dev/spidev0.1`) に切り替えるか、ソフトウェア SPI を検討してください。

### 7.3 LED を使わない構成

LED 配線を行わない場合は `config.json` で `led_settings.enabled = false` にしてください。`SPI_AVAILABLE` (`src/keyboard_proxy.py` 内、`spidev` import 失敗で False) が False の環境では LED 関連処理は完全にスキップされ、警告ログが残るのみで本体機能は通常どおり動作します。

### 7.4 ボタン数を増減したい

現状 3 ボタン固定です。増やすには `KeyBowManager` クラスに `btn4` 以降と対応するハンドラを追加し、`button_states` 辞書も拡張する必要があります。設計の詳細は [DEVELOPMENT.md](DEVELOPMENT.md) を参照してください。

### 7.5 LED は APA102。WS2812B / NeoPixel ではない

過去の commit で誤って `rpi_ws281x` (WS2812B 専用) が導入された期間があり、その名残がドキュメントの随所に残っていた可能性があります。本プロジェクトの正規のターゲットは **Pimoroni Keybow Mini = APA102 (SPI)** です。WS2812B を使いたい場合は `LedStatusManager` を `rpi_ws281x` ベースで書き直すこと。
