import time
import board
import rotaryio
import digitalio
from cedargrove_nau7802 import NAU7802

# ============================================================================
#  Grind-by-Weight controller
#
#  Turn the rotary dial to choose a target weight in 0.1 g increments.
#  While the scale reads LESS than the target, the Port B output is driven
#  HIGH ('1') -- e.g. to run the grinder.  As soon as the measured weight
#  reaches or exceeds the target, the output goes LOW ('0').
# ============================================================================

# ------------------------------------------------------- calibration constants
#  Obtain these from unSyncedUtils/scale_test.py and paste the values below.
ZERO_OFFSET = 591116       # raw counts with an empty pan
COUNTS_PER_GRAM = 6124.6440  # raw counts per gram

# ----------------------------------------------------------------- set point
GRAMS_PER_DETENT = 0.1     # weight change per encoder click
MIN_SETPOINT = 0.0         # dial can't go below this
MAX_SETPOINT = 5000.0      # ...or above this

# --------------------------------------------------------------- scale config
ACTIVE_CHANNEL = 1         # NAU7802 channel wired to the load cell (1 or 2)
SMOOTHING = 10             # readings kept in the moving average (steadier = larger)
ENCODER_SIGN = -1          # clockwise increases weight (this unit counts down CW)

# ---------------------------------------------------------------- hardware init
# Rotary encoder on the confirmed onboard pins.
encoder = rotaryio.IncrementalEncoder(board.ENC_A, board.ENC_B)
last_position = encoder.position

# Rear Port B digital output (GPIO2).  Starts LOW.
portb = digitalio.DigitalInOut(board.PORTB_OUT)
portb.direction = digitalio.Direction.OUTPUT
portb.value = False

# NAU7802 scale on Port A (explicit routing per CLAUDE.md).
i2c = board.PORTA_I2C()
scale = NAU7802(i2c, address=0x2A, active_channels=1)
if not scale.enable(True):
    print("!! NAU7802 did not report ready; continuing anyway.")
scale.channel = ACTIVE_CHANNEL
scale.calibrate("INTERNAL")    # required ADC self-calibration

# ------------------------------------------------------------- running state
set_point = 20.0               # current target weight in grams (startup default)
samples = []                   # moving-average buffer of gram readings
weight = 0.0                   # latest smoothed weight in grams


def clamp(value, low, high):
    return max(low, min(high, value))


def draw(target, grams, output_on):
    """Redraw the serial console status panel."""
    print("\033[2J\033[H")
    print("==============================")
    print("      GRIND BY WEIGHT         ")
    print("==============================")
    print("Set point : {:8.1f} g".format(target))
    print("Weight    : {:8.1f} g".format(grams))
    print("Output    : {}  ({})".format(
        int(output_on), "GRINDING" if output_on else "STOPPED"))


# --------------------------------------------------------------- initial paint
draw(set_point, weight, portb.value)
last_draw = time.monotonic()

# --------------------------------------------------------------- control loop
while True:
    dirty = False

    # 1. Update the target from the dial.  Accumulate the delta so turning
    #    below zero and back up has no dead-zone at the clamp.
    position = encoder.position
    if position != last_position:
        set_point += ENCODER_SIGN * (position - last_position) * GRAMS_PER_DETENT
        set_point = round(clamp(set_point, MIN_SETPOINT, MAX_SETPOINT), 1)
        last_position = position
        dirty = True

    # 2. Fold any new conversion into the moving average (non-blocking).
    if scale.available():
        grams = (scale.read() - ZERO_OFFSET) / COUNTS_PER_GRAM
        samples.append(grams)
        if len(samples) > SMOOTHING:
            samples.pop(0)
        weight = sum(samples) / len(samples)
        dirty = True

    # 3. Drive the output: HIGH while under target, LOW once reached/exceeded.
    output_on = weight < set_point
    if output_on != portb.value:
        portb.value = output_on
        dirty = True

    # 4. Refresh the display at most ~5x/second when something changed.
    now = time.monotonic()
    if dirty and (now - last_draw) >= 0.2:
        draw(set_point, weight, portb.value)
        last_draw = now

    time.sleep(0.01)
