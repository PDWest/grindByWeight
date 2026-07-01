# M5 Dial + SparkFun Qwiic Scale — Integration Notes

Working notes for wiring and reading a load cell on the M5Stack Dial via the
SparkFun Qwiic Scale (NAU7802) on Port A. Covers the encoder behavior, the
5 V/3.3 V power problem, part selection, and the test/calibration program.

---

## 1. Encoder behavior (`code.py`)

### Is `encoder.position` an absolute value?
Yes. `rotaryio.IncrementalEncoder.position` is an **absolute, cumulative** count,
not a per-loop delta.

- Starts at `0` when the encoder object is created.
- `+1` per detent clockwise, `-1` per detent counterclockwise.
- Can go **negative** (turning CCW past the start point).
- Persists until you reassign it (`encoder.position = 0`) or reboot.
- It's absolute relative to **power-on position**, not an absolute angle on the
  dial — there is no physical index/home reference.

Because `position` is the running total, `code.py` diffs it against
`last_position` to detect movement.

### What if 1.5 revolutions happen between reads?
You see the **full 1.5 revolutions' worth of counts**, not a fraction.

- `rotaryio` counts in the **background** using the ESP32-S3 hardware pulse
  counter (PCNT), independent of the Python loop. Reading `position` just
  samples a total that already accumulated.
- Slow polling (`time.sleep(0.01)`) never drops counts — it only changes how
  often you *observe* the total.
- You lose the **path**, not the **magnitude**: if the knob went +30 then −15
  between reads, you only see the net (+15). Intermediate reversals that cancel
  out aren't visible.
- "Revolution" is not a native unit — `position` is in counts/detents. Counts
  per physical revolution depends on the encoder's resolution.
- The only way to actually lose counts is to exceed the hardware counter's speed
  limit — not reachable by a human hand. This is the advantage over reading raw
  GPIO pins in the loop, where slow polling *would* miss transitions.

---

## 2. Load cell → SparkFun Qwiic Scale (SEN-15242)

A 4-wire load cell is a Wheatstone bridge: Excitation+ (E+), Excitation− (E−),
Signal+ (O+), Signal− (O−). The Qwiic Scale board is silkscreened
**RED / BLK / WHT / GRN**. For a standard cell, match colors to the labels:

| Wire  | Bridge function   | SEN-15242 terminal |
|-------|-------------------|--------------------|
| Red   | Excitation +      | RED                |
| Black | Excitation −      | BLK                |
| Green | Signal / Output + | GRN                |
| White | Signal / Output − | WHT                |

### Verify wires if colors are nonstandard (ohmmeter)
- The two **excitation** wires read the full bridge resistance between them
  (often ~1 kΩ or ~350 Ω, depending on the cell).
- The two **signal** wires read roughly the same full-bridge value.
- Any excitation-to-signal pair reads a **lower, in-between** value (~75%).

Find the two pairs with the highest matching resistance — one pair is E+/E−, the
other is O+/O−. Which wire is + vs − within the signal pair only affects the
**sign** of the reading (swap green/white if weight reads negative).

---

## 3. M5 Dial Port A pinout

Port A is the **red Grove I²C port (HY2.0-4P)**. M5Stack cable colors:

| Wire color | Function | M5 Dial net | CircuitPython   |
|------------|----------|-------------|-----------------|
| Black      | GND      | GND         | —               |
| Red        | VCC      | **5 V**     | —               |
| Yellow     | SDA      | GPIO 13     | `board.PORTA_SDA` |
| White      | SCL      | GPIO 15     | `board.PORTA_SCL` |

- Bus init shortcut: `board.PORTA_I2C()` (pairs GPIO 13 / GPIO 15).
- **VCC is 5 V**; **SDA/SCL logic is 3.3 V** (ESP32-S3 GPIO are 3.3 V-only).
- Across a Grove-to-Qwiic adapter, match by **function**, not color (Qwiic uses
  black GND / red 3.3 V / blue SDA / yellow SCL).

---

## 4. The 5 V / 3.3 V power problem

**Measured: 5 V between red and black on Port A.**

### Why you can't wire the Qwiic Scale straight in
The Qwiic Scale has **no onboard level shifting** and its I²C pull-ups go to
whatever powers its VDD. Power it from Port A's 5 V and the pull-ups hold
SDA/SCL **at 5 V when idle** — those lines connect to GPIO 13/15, which are
**3.3 V-only, not 5 V-tolerant**. That can damage the Dial. The NAU7802 *chip*
survives 5 V (max 5.5 V); the danger is purely the pull-ups back-driving the
Dial's I²C pins.

### The rule
Power the NAU7802 board at **3.3 V** so its pull-ups reference 3.3 V, and connect
**only SDA, SCL, and GND** to Port A. **Do not connect Port A's 5 V to the
board's VCC.** Running the NAU7802 at 3.3 V is normal (SparkFun's own examples
do it).

### Why Port A is 5 V power + 3.3 V logic (not a design bug)
This is deliberate, standard M5Stack design:

- ESP32-S3 GPIO are 3.3 V-only, so I²C lines *must* be 3.3 V. But many
  peripherals want 5 V power — so M5Stack routes 5 V power + 3.3 V logic on the
  same Grove connector across their whole ecosystem.
- The I²C **pull-ups live on the Dial's mainboard, tied to 3.3 V.** The bus is a
  proper 3.3 V bus; the 5 V pin is just a power rail riding alongside.
- M5Stack's own "Units" are built for this: they regulate the 5 V down to 3.3 V
  **internally** for their sensors and rely on the mainboard's 3.3 V pull-ups
  rather than adding their own 5 V pull-ups.
- The SparkFun board is the odd one out because it carries **its own pull-ups
  tied to VDD**. Powering it at 5 V injects 5 V pull-ups onto a 3.3 V bus.
- Adding a 3.3 V regulator makes the SparkFun board behave like a proper M5
  Unit: drop 5 V → 3.3 V locally so its pull-ups reference 3.3 V.
- Irony: SparkFun invented **Qwiic as a uniform 3.3 V standard** to avoid exactly
  this mismatch; plugging Qwiic into a 5 V-powered Grove port reintroduces it —
  which is why the jump needs a regulator, not just an adapter cable.

---

## 5. Getting a 3.3 V rail — part options

### Option A — Inline 5 V→3.3 V regulator (recommended, self-contained)
- Port A **5 V (red)** + **GND (black)** → regulator input.
- Regulator **3.3 V output → Scale VCC**.
- Port A **SDA (G13)/SCL (G15) → Scale SDA/SCL** directly.
- Tie **all grounds** common.

### Option B — Separate 3.3 V supply (zero-cost if available)
- Power Scale VCC from any 3.3 V source; common the grounds; run SDA/SCL/GND to
  Port A; leave Port A's 5 V disconnected.

### What NOT to do
- ❌ Connect Port A 5 V to Scale VCC and run I²C directly.
- ❌ Rely on the ESP32's clamp diodes to "absorb" 5 V.
- ❌ Cut the board's pull-up jumper and still feed 5 V logic.

### Level translator (PCA9306) — why it's not the fix here
A PCA9306 works as a bidirectional I²C translator (VREF1 = 3.3 V low side,
VREF2 = 5 V high side) and would protect the Dial. **But VREF1 still needs a real
3.3 V rail** — Port A only provides 5 V. And if you already have 3.3 V, you'd
just power the Scale at 3.3 V and skip translation entirely. The NAU7802 has no
reason to run at 5 V, so the translator is extra parts that *still* need a 3.3 V
source. Buy a regulator, not a translator.

### Regulator part notes

**Chanzon 78L33 (bare TO-92)** — acceptable, given ~10 mA load:
- 100 mA capable (you need ~5–12 mA), runs cold (~20 mW).
- Not a true LDO (~1.7 V dropout); at 5 V→3.3 V the margin is thin on paper, but
  dropout shrinks at low current, so it regulates fine here.
- **Add decoupling caps** or it may oscillate: ~0.33 µF (or 1 µF) input→GND,
  ~0.1 µF (1–10 µF safer) output→GND.
- ⚠️ **TO-92 pinout is reversed** from big 78xx parts. Flat face toward you,
  legs down: **Pin 1 = OUTPUT, Pin 2 = GND, Pin 3 = INPUT**. Wiring input to
  pin 1 destroys it.

**AMS1117-3.3 module (recommended)** — search "AMS1117 3.3V module":
- Despite listings saying "DC-DC Buck Converter," the AMS1117 is a **linear
  LDO** — mislabeled, but *good* for you (low noise for a 24-bit ADC).
- Input ~4.5–7 V (Port A 5 V fits), fixed 3.3 V out, up to 800 mA–1 A.
- Dropout ~1.1–1.3 V → comfortable 1.7 V headroom from 5 V.
- **Onboard input/output caps** (no caps to add) and **labeled IN/GND/OUT
  headers** (no pinout guessing). Lower-effort than the bare 78L33.

Avoid adjustable buck modules (MP1584 / mini-360) for this — switching ripple
into a sensitive scale ADC plus pot-trim/drift risk.

### Final wiring (with AMS1117 module)
```
Port A Red (5V) ─────────► module IN
Port A Black (GND) ──┬────► module GND
                     └────► Scale GND      (common ground)
module OUT (3.3V) ───────► Scale VCC (3.3V)
Port A Yellow (SDA/G13) ─► Scale SDA
Port A White  (SCL/G15) ─► Scale SCL
```
Before connecting the Scale, power the module and **measure OUT-to-GND ≈ 3.3 V**.
Then plug in the Scale.

---

## 6. Test & calibration program (`scale_test.py`)

A stand-alone utility (leaves `code.py` untouched). It:
1. Scans I²C and confirms the NAU7802 answers at **0x2A** (halts with a wiring
   checklist if not).
2. Enables the ADC and runs `calibrate("INTERNAL")`.
3. **Tares** with an empty pan → `ZERO_OFFSET` (averaged).
4. **Calibrates span** with a known weight → `COUNTS_PER_GRAM`.
5. Prints the two constants, then **streams live grams** (Ctrl-C to stop).

### Running it
CircuitPython only auto-runs `code.py`, so either:
- Copy `scale_test.py` to `CIRCUITPY`, open the serial console, and `import
  scale_test` at the REPL, **or**
- Temporarily rename it to `code.py` to run on boot.

A connected console is required (the calibration steps use `input()`).

### Key API (cedargrove_nau7802)
```python
i2c = board.PORTA_I2C()
scale = NAU7802(i2c, address=0x2A, active_channels=1)
scale.enable(True)                 # power up ADC
scale.channel = 1                  # select channel (1 or 2)
scale.calibrate("INTERNAL")        # required ADC self-cal
while not scale.available():       # data-ready poll
    pass
raw = scale.read()                 # signed 24-bit reading
```

### Using the results in your main program
```python
grams = (average_reading(scale) - ZERO_OFFSET) / COUNTS_PER_GRAM
```

### Tuning / gotchas
- **Averaging** (`SAMPLES`, default 100) is the main noise defense — raise for
  steadier readings, lower for faster response.
- **Negative grams** on a downward push → green/white (O+/O−) swapped (harmless;
  swap for positive raw counts).
- **Tiny delta** under a known weight → likely load-cell wiring/mounting problem.

---

## Reference — hardware summary

| Item | Value |
|------|-------|
| Board | M5Stack Dial (V1.1), ESP32-S3 (StampS3A), board ID `m5stack_dial` |
| Firmware | Adafruit CircuitPython 10.3+ |
| Scale | SparkFun Qwiic Scale — NAU7802 (SEN-15242) |
| I²C address | `0x2A` |
| Bus | Port A, `board.PORTA_I2C()` — SDA GPIO 13, SCL GPIO 15 |
| Port A power | 5 V (must regulate to 3.3 V for the Scale) |
| Driver lib | `cedargrove_nau7802` (in `/lib/`) |
