# SPDX-License-Identifier: MIT
"""
scale_test.py -- Test & calibration utility for the SparkFun Qwiic Scale
(NAU7802) attached to Port A of the M5Stack Dial.

Run it from the serial console (REPL). It will:
  1. Scan the I2C bus and confirm the NAU7802 answers at 0x2A.
  2. Power up and internally calibrate the ADC.
  3. Tare (capture the zero offset) with the pan empty.
  4. Ask you to place a known weight and derive a counts-per-gram factor.
  5. Stream live weight so you can verify accuracy.

At the end it prints the two constants you need --
    ZERO_OFFSET and COUNTS_PER_GRAM
-- so you can paste them into your main program and skip re-calibrating.

Wiring assumes the Scale is powered at 3.3V (via an external regulator),
with SDA/SCL/GND on Port A.  See CLAUDE.md.
"""

import time
import board
from cedargrove_nau7802 import NAU7802

# ---------------------------------------------------------------- configuration
NAU7802_ADDR = 0x2A     # fixed hardware address of the Qwiic Scale
ACTIVE_CHANNEL = 1      # NAU7802 channel wired to the load cell (1 or 2)
SAMPLES = 100           # readings averaged per measurement (more = steadier)


# --------------------------------------------------------------------- helpers
def scan_i2c(i2c):
    """Return a list of 7-bit addresses currently on the bus."""
    while not i2c.try_lock():
        pass
    try:
        return i2c.scan()
    finally:
        i2c.unlock()


def average_reading(scale, samples=SAMPLES):
    """Block until `samples` conversions are collected; return their mean."""
    total = 0
    for _ in range(samples):
        while not scale.available():
            pass
        total += scale.read()
    return total / samples


def wait_for_enter(prompt):
    """Pause until the user presses Enter in the serial console."""
    try:
        input(prompt)
    except EOFError:
        # No serial console attached -- fall back to a short delay.
        print(prompt + "  (no console; continuing in 5s)")
        time.sleep(5)


# ------------------------------------------------------------------------ setup
print("\n=== NAU7802 Scale Test & Calibration ===\n")

i2c = board.PORTA_I2C()          # explicit Port A routing (GPIO13 / GPIO15)

print("Scanning I2C bus on Port A...")
found = scan_i2c(i2c)
print("  Devices found:", [hex(a) for a in found])

if NAU7802_ADDR not in found:
    print("\n!! NAU7802 (0x2A) NOT found. Check:")
    print("   - Scale powered at 3.3V (NOT Port A's 5V)")
    print("   - SDA->G13, SCL->G15, grounds common")
    print("   - Regulator output actually reads ~3.3V")
    raise SystemExit

print("  NAU7802 found at 0x2A.\n")

# Bring the ADC up and run its internal offset/gain self-calibration.
scale = NAU7802(i2c, address=NAU7802_ADDR, active_channels=1)
print("Enabling ADC...")
if not scale.enable(True):
    print("!! ADC did not report ready; continuing anyway.")
scale.channel = ACTIVE_CHANNEL
scale.calibrate("INTERNAL")      # required ADC self-calibration
print("  ADC enabled, channel", ACTIVE_CHANNEL, "internally calibrated.\n")


# -------------------------------------------------------------------- tare/zero
wait_for_enter(">> Remove ALL weight from the pan, then press Enter to tare...")
zero_offset = average_reading(scale)
print("  Zero offset (raw counts):", int(zero_offset), "\n")


# ------------------------------------------------------------------- span/scale
wait_for_enter(">> Place a KNOWN weight on the pan, then press Enter...")
try:
    known_grams = float(input("   Enter the weight in grams (e.g. 100): "))
except (ValueError, EOFError):
    known_grams = 100.0
    print("   Using default:", known_grams, "g")

loaded = average_reading(scale)
delta = loaded - zero_offset
print("  Loaded reading (raw):", int(loaded))
print("  Delta from zero     :", int(delta))

if abs(delta) < 1000:
    print("\n!! Delta is very small -- did the weight actually load the cell?")
    print("   Check the load-cell wiring (E+/E-/O+/O-) and mounting.\n")

counts_per_gram = delta / known_grams
print("  Counts per gram     : {:.3f}".format(counts_per_gram))

if counts_per_gram < 0:
    print("  (Negative -> load-cell O+/O- are swapped. Harmless; the math still")
    print("   works, but swap the green/white wires for positive raw counts.)")

print("\n--- Calibration constants (paste into your main program) ---")
print("ZERO_OFFSET     = {:d}".format(int(zero_offset)))
print("COUNTS_PER_GRAM = {:.4f}".format(counts_per_gram))
print("-----------------------------------------------------------\n")


# ------------------------------------------------------------ live verification
print("Streaming live weight.  Ctrl-C to stop.\n")
try:
    while True:
        raw = average_reading(scale, samples=20)   # fewer samples = snappier
        grams = (raw - zero_offset) / counts_per_gram
        print("  {:8.1f} g   (raw {:>9d})".format(grams, int(raw)))
        time.sleep(0.25)
except KeyboardInterrupt:
    print("\nDone.")
