# ハードウェア配線ガイド

本ドキュメントは Rpi-Multi-Device-HID-Proxy で使用するハードウェアの選定と物理配線をまとめたものです。設定値の変更方法は [CONFIGURATION.md](CONFIGURATION.md)、ソフトウェアのインストールは [INSTALL.md](INSTALL.md) を参照してください。

## 1. 必要な部品（BOM）

| 部品 | 数量 | 補足 |
|---|---|---|
| Raspberry Pi Zero 2W | 1 | OTG 対応モデルなら Pi 4 / Pi 5 / Pi Zero / Pi Zero W でも可 |
| microSD カード | 1 | 8 GB 以上、Class 10 以上推奨 |
| USB OTG ケーブル | 1 | **データ通信対応**のものを選ぶこと（充電専用ケーブルは不可） |
| タクトスイッチ | 3 | 操作ボタン用（短押し/長押し検出） |
| WS2812B NeoPixel LED | 3 | ステータス表示用（5V / 3pin タイプ） |
| ジャンパ線 | 適量 | デュポンメス〜オスやはんだ付けに応じて |
| 抵抗 330–470 Ω | 1 | LED データ線の保護用（推奨、必須ではない） |
| 電源 | 1 | Pi の給電用（OTG ポートを USB ガジェットとして使う場合は別途給電が必要なケースあり） |

### 既製品との対応
- **Pimoroni Keybow / Pibow**: ボタン位置を本実装の Btn1/2/3 にマップ可能。GPIO 番号がコードとずれる場合があるため要再配線。
- **HHKB Studio + Logitech マウス**: 上流入力デバイスとして動作確認済み（`udev/99-mouse-proxy.rules` に対応ルールあり）。

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

ボタン番号、GPIO 番号、物理ピン番号、機能の対応は以下のとおりです（実装ソース: `src/keyboard_proxy.py:446-458`）。

| ボタン | GPIO 番号 | 物理ピン番号 | 短押し動作 | 長押し動作 |
|---|---|---|---|---|
| Btn1 | **GPIO 6** | 31 | Alt+A 送信 | リマップ機能の有効/無効トグル |
| Btn2 | **GPIO 22** | 15 | Alt+Y 送信 | （単独では未割当） |
| Btn3 | **GPIO 17** | 11 | Space 送信 | （単独では未割当） |
| Btn1+Btn2 | — | — | — | メールアドレス自動入力 |
| Btn1+Btn3 | — | — | — | システムシャットダウン |

実装ソース: 短押し/長押しの分岐は `src/keyboard_proxy.py:595-707`。長押し判定時間と短押し時のチャタリング防止時間は `config.json` の `gpio_settings` で調整できます（[CONFIGURATION.md](CONFIGURATION.md#gpio_settings) 参照）。

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

`gpiozero.Button` のデフォルトは `pull_up=True` なので、Pi 内部のプルアップ抵抗が有効になり、**外部抵抗は不要**です（実装: `src/keyboard_proxy.py:55-62`）。

### GND 共通

3 つのボタンと NeoPixel LED の GND は共通にして構いません。Pi 側の GND ピンは物理 6/9/14/20/25/30/34/39 のいずれを使ってもよく、配線の取り回しに合わせて選んでください。

## 4. NeoPixel LED 配線

LED はリマップ機能の有効/無効をユーザーに視覚的に通知するために使います（実装ソース: `src/keyboard_proxy.py:467-485, 683-707`）。

| 信号 | 接続先 | 物理ピン番号 |
|---|---|---|
| **データ (DIN)** | **GPIO 18** | 12 |
| **5V 電源 (VCC)** | 5V | 2 または 4 |
| **GND** | GND | 6 / 9 / 14 / 20 / 25 / 30 / 34 / 39 のいずれか |

実装は `rpi_ws281x.PixelStrip` を使用しており、信号周波数は **800 kHz** (WS2812B 標準)、DMA チャネルは **10** を使用します（`src/keyboard_proxy.py:478-485`）。

### 配線図

```
   Raspberry Pi (40-pin header)         WS2812B NeoPixel ×3
   ┌───────────────────┐                ┌──────┬──────┬──────┐
   │                   │                │ LED1 │ LED2 │ LED3 │
   │ pin 2 (5V)    ────┼─── VCC ───────▶│ 5V   │ 5V   │ 5V   │
   │ pin 12 (GPIO18)───┼─[330Ω]─ DIN ──▶│ DIN  │      │      │
   │                   │                │ DOUT─┼─DIN  │      │
   │                   │                │      │ DOUT─┼─DIN  │
   │ pin 6 (GND)   ────┼─── GND ───────▶│ GND  │ GND  │ GND  │
   └───────────────────┘                └──────┴──────┴──────┘
```

LED 数はデフォルト 3 個ですが、`config.json` の `led_settings.led_count` で変更可能です（[CONFIGURATION.md](CONFIGURATION.md#led_settings)）。

### LED の状態表示

| 状態 | 色（デフォルト） | 配列 |
|---|---|---|
| リマップ機能 **有効** | 緑 | `[0, 255, 0]` |
| リマップ機能 **無効** | 赤 | `[255, 0, 0]` |

色は `config.json` の `led_settings.colors` で変更できます。

### レベルシフタについて

WS2812B のロジック High は通常 0.7 × VCC ≈ 3.5 V で、Pi の GPIO 出力 3.3 V でもほとんどの個体は反応しますが、長距離配線や複数本接続では誤動作することがあります。安定動作には **74AHCT125** などのレベルシフタを Pi の GPIO18 と LED1 の DIN の間に挟むことを推奨します。

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
      GPIO17 11 │ ◉  ●  │  12  GPIO18     <-- Btn3=GPIO17 / LED DIN=GPIO18
      GPIO27 13 │ ●  ●  │  14  GND
      GPIO22 15 │ ◉  ●  │  16  GPIO23     <-- Btn2=GPIO22
        3V3  17 │ ●  ●  │  18  GPIO24
      GPIO10 19 │ ●  ●  │  20  GND
       GPIO9 21 │ ●  ●  │  22  GPIO25
      GPIO11 23 │ ●  ●  │  24  GPIO8
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

### 6.2 NeoPixel LED

```bash
# rpi_ws281x がインストール済みであること
# sudo pip3 install --break-system-packages rpi_ws281x
sudo python3 - <<'PY'
from rpi_ws281x import PixelStrip, Color
strip = PixelStrip(3, 18, 800000, 10, False, 50)
strip.begin()
for c in [(255,0,0), (0,255,0), (0,0,255)]:
    for i in range(3):
        strip.setPixelColor(i, Color(*c))
    strip.show()
    import time; time.sleep(1)
PY
```

赤 → 緑 → 青の順で 3 つの LED が点灯することを確認します。

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

ボタン (`GPIO 6 / 22 / 17`) と LED (`GPIO 18`) の番号は `src/keyboard_proxy.py:446-456, 467` でハードコードされています。LED ピンのみ `config.json` の `led_settings.gpio_pin` で上書きできますが、ボタン側はソース改変が必要です。

別の GPIO に変えたい場合は `KeyBowManager.__init__` の `Button(N)` を編集してください。

### 7.2 PWM0 占有によるオーディオ競合

`rpi_ws281x` は GPIO18 (PWM0) を使うため、Pi 本体の PWM オーディオ出力と競合します。LED を有効にしている間は HDMI/USB 経由のオーディオ出力に切り替える必要があります。

代替策: `rpi_ws281x` の DMA 設定を変えて GPIO12/13/19 (PWM1, PCM 系) を使うことも可能ですが、本実装では未対応です。

### 7.3 LED を使わない構成

LED 配線を行わない場合は `config.json` で `led_settings.enabled = false` にしてください。`NEOPIXEL_AVAILABLE` (`src/keyboard_proxy.py:65 付近`) が False の環境では LED 関連処理は完全にスキップされます。

### 7.4 ボタン数を増減したい

現状 3 ボタン固定です。増やすには `KeyBowManager` クラスに `btn4` 以降と対応するハンドラを追加し、`button_states` 辞書も拡張する必要があります。設計の詳細は [DEVELOPMENT.md](DEVELOPMENT.md) を参照してください。
