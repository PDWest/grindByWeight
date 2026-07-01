# Project Environment & Hardware Specs

## Core Target System
- **Microcontroller Board:** M5Stack Dial (V1.1) Smart Rotary Knob
- **Core Processor:** Espressif ESP32-S3 (StampS3A Controller Module)
- **Firmware Environment:** Adafruit CircuitPython (Target version: 9.x+)
- **Board ID:** `m5stack_dial`

## Connected Hardware & External Sensors
- **External Sensor:** SparkFun Qwiic Scale - NAU7802 (Product ID: SEN-15242)
- **Sensor Type:** 24-bit Dual-Channel Analog-to-Digital Converter for Load Cells / Weight Scales
- **I2C Address:** `0x2A` (Hardware defined)

## Peripheral Wiring & Pin Mappings (CircuitPython `board`)
The external SparkFun sensor is connected via the physical JST-PH 4-pin **PORT A** (red I2C grove port) on the back of the M5Stack Dial.

- **I2C Bus Configuration:**
    - `SDA` Pin: `board.PORTA_SDA` (GPIO 13)
    - `SCL` Pin: `board.PORTA_SCL` (GPIO 15)
    - Native initialization shortcut: `board.PORTA_I2C()`

- **Onboard Peripherals (Reference Only):**
    - Encoder Phase A: GPIO 40
    - Encoder Phase B: GPIO 41
    - Encoder Push Button: `board.BTN` (GPIO 42)
    - Display Driver: GC9A01 (SPI bus)
    - RFID Reader: WS1850S (SPI bus)

## Required CircuitPython Libraries (`/lib/`)
When writing code extensions, assume the following modules are loaded and accessible:
- `board` and `busio` (Core hardware access)
- `cedargrove_nau7802` (Community library for the SparkFun NAU7802 scale driver)

## Architectural Code Guidelines
1. **Always use explicit I2C initialization:** Initialize using `board.PORTA_I2C()` rather than generic `board.I2C()` to guarantee correct hardware routing.
2. **Resource Management:** CircuitPython handles memory dynamically. Avoid keeping unused or heavy graphical objects active if you are doing high-frequency sampling from the scale.
3. **Scale Reading Routine:** The NAU7802 should be polled asynchronously or via simple loops rather than interrupts. Use calibration values and zero-offsets explicitly at startup.
