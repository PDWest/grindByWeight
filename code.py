import time
import board
import rotaryio
import digitalio
import keypad
import microcontroller
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
CONVERSION_RATE = 80      # hardware sample rate, SPS (10/20/40/80/320)
SAMPLE_COUNT = 16          # readings per median-filtered measurement
DECISION_PERIOD = 0.1      # seconds between weight decisions + display updates
ENCODER_SIGN = -1          # clockwise increases weight (this unit counts down CW)

# ---------------------------------------------------------------- hardware init
# Rotary encoder on the confirmed onboard pins.
encoder = rotaryio.IncrementalEncoder(board.ENC_A, board.ENC_B)

# Rear Port B digital output (GPIO2).  Starts LOW.
portb = digitalio.DigitalInOut(board.PORTB_OUT)
portb.direction = digitalio.Direction.OUTPUT
portb.value = False

# Bezel push button on GPIO42.  keypad.Keys handles debounce and edge events;
# value_when_pressed=False because the button grounds the pin when pressed.
bezel_button = keypad.Keys(
    (microcontroller.pin.GPIO42,),
    value_when_pressed=False,
    pull=True,
)

# NAU7802 scale on Port A (explicit routing per CLAUDE.md).
i2c = board.PORTA_I2C()
scale = NAU7802(i2c, address=0x2A, active_channels=1)
if not scale.enable(True):
    print("!! NAU7802 did not report ready; continuing anyway.")
scale.channel = ACTIVE_CHANNEL
scale.conversion_rate = CONVERSION_RATE   # set rate before calibrating
scale.calibrate("INTERNAL")               # required ADC self-calibration

# ------------------------------------------------------------- running state
set_point = 20.0               # current target weight in grams (startup default)
last_position = encoder.position
weight = 0.0                   # latest filtered weight in grams
window = []                    # sliding window of the most recent raw counts


def clamp(value, low, high):
    return max(low, min(high, value))


def update_setpoint():
    """Poll the dial and adjust the target. Called often to stay responsive."""
    global set_point, last_position
    position = encoder.position
    if position != last_position:
        # Accumulate the delta so turning below zero and back has no dead-zone.
        set_point += ENCODER_SIGN * (position - last_position) * GRAMS_PER_DETENT
        set_point = round(clamp(set_point, MIN_SETPOINT, MAX_SETPOINT), 1)
        last_position = position


def poll_scale():
    """Drain any ready conversions into the sliding window (newest at the end).

    Runs every loop pass, so the window continuously tracks the most recent
    SAMPLE_COUNT raw readings regardless of how often we compute a median.
    """
    global window
    while scale.available():
        window.append(scale.read())
    if len(window) > SAMPLE_COUNT:
        window = window[-SAMPLE_COUNT:]


def median_raw():
    """Median raw count of the current window (assumes window is non-empty)."""
    ordered = sorted(window)
    return ordered[len(ordered) // 2]


def filtered_weight():
    """Median of the current window, in grams. Rejects single-sample spikes."""
    if not window:
        return weight              # no samples yet; keep the last value
    return (median_raw() - ZERO_OFFSET) / COUNTS_PER_GRAM


def tare():
    """Zero the scale: set the offset to the current median raw reading."""
    global ZERO_OFFSET, weight
    if window:
        ZERO_OFFSET = median_raw()
        weight = 0.0
        portb.value = weight < set_point
        draw_values(set_point, weight, portb.value)   # immediate feedback


def check_button():
    """Tare on each press of the bezel button (keypad handles debounce)."""
    event = bezel_button.events.get()
    if event and event.pressed:
        tare()


# Console layout: 1-based rows of the changing values, and the column where
# each value begins (just past the 12-character labels below).
ROW_SETPOINT = 5
ROW_WEIGHT = 6
ROW_OUTPUT = 7
VALUE_COL = 13


def draw_static():
    """Clear the screen and print the banner + labels once."""
    print("\033[2J\033[H")
    print("==============================")
    print("      GRIND BY WEIGHT         ")
    print("==============================")
    print("Set point : ")
    print("Weight    : ")
    print("Output    : ")
    


def draw_values(target, grams, output_on):
    """Overwrite only the changing values in place (labels stay put)."""
    # \033[<row>;<col>H positions the cursor; \033[K clears to end of line.
    print("\033[{};{}H\033[K{:8.1f} g".format(
        ROW_SETPOINT, VALUE_COL, target), end="")
    print("\033[{};{}H\033[K{:8.1f} g".format(
        ROW_WEIGHT, VALUE_COL, grams), end="")
    print("\033[{};{}H\033[K{}  ({})".format(
        ROW_OUTPUT, VALUE_COL, int(output_on),
        "GRINDING" if output_on else "STOPPED"), end="")
    # Park the cursor on a blank line below so it isn't sitting in a value field.
    print("\033[9;1H", end="")


# --------------------------------------------------------------- initial paint
draw_static()
draw_values(set_point, weight, portb.value)
last_tick = time.monotonic()

# --------------------------------------------------------------- control loop
while True:
    # Keep the dial responsive and the sample window fresh every pass.
    update_setpoint()
    poll_scale()
    check_button()

    now = time.monotonic()
    if now - last_tick >= DECISION_PERIOD:
        last_tick = now

        # Median-filter the current window and decide the output:
        # HIGH while under target, LOW once the target is reached/exceeded.
        weight = filtered_weight()
        portb.value = weight < set_point

        draw_values(set_point, weight, portb.value)

    time.sleep(0.005)
