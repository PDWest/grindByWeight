import time
import math
import board
import rotaryio
import digitalio
import displayio
import terminalio
import adafruit_focaltouch
from adafruit_display_text import label
from vectorio import Rectangle
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

# Capacitive touch screen (FocalTech FT6336U) on the board's internal I2C bus.
# A touch anywhere on the screen tares the scale.  The FT6336U can take a few
# seconds to wake and answer at 0x38 after a soft reboot, so retry the probe for
# up to ~4 s before giving up; if it never appears, touch-to-tare is disabled.
touch_i2c = board.I2C()
touch = None
for _attempt in range(20):
    try:
        touch = adafruit_focaltouch.Adafruit_FocalTouch(touch_i2c)
        break
    except (ValueError, OSError):
        time.sleep(0.2)
if touch is None:
    print("!! Touch controller not found at 0x38; touch-to-tare disabled.")

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
running = False                # START/STOP latch (toggled by lower-half taps)


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
    try:
        while scale.available():
            window.append(scale.read())
    except OSError:
        # Transient I2C glitch (EIO); skip this pass and retry next loop.
        return
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


def apply_output():
    """Engage the grinder only while started AND still under the target."""
    portb.value = running and (weight < set_point)


def tare():
    """Zero the scale: set the offset to the current median raw reading."""
    global ZERO_OFFSET, weight
    if window:
        ZERO_OFFSET = median_raw()
        weight = 0.0
        apply_output()
        draw_values(set_point, weight, running)       # immediate feedback


def toggle_running():
    """Flip the START/STOP latch (lower-half tap) and update output at once."""
    global running
    running = not running
    apply_output()
    draw_values(set_point, weight, running)


_touch_was_down = False        # edge-detect state for the touch screen
touch_x = -1                   # last touch location in screen pixels;
touch_y = -1                   # (-1, -1) means "no touch seen yet"


def check_touch():
    """Dispatch a new screen touch by region and record its location.

    Upper half taps tare the scale; lower half taps toggle START/STOP.  Uses
    touch.touches (the safe coordinate array) rather than touch.points, which
    can crash this controller's register reads.  touch_x / touch_y hold the
    most recent location and update continuously while a finger is down.
    """
    global _touch_was_down, touch_x, touch_y
    if touch is None:
        return                 # touch controller absent; nothing to do
    try:
        active = bool(touch.touched)
        if active:
            points = touch.touches
            if points:
                touch_x = points[0]["x"]
                touch_y = points[0]["y"]
    except OSError:
        return                 # transient I2C glitch; try again next pass
    if active and not _touch_was_down:
        if touch_y < CY:
            tare()             # upper half: zero the scale
        else:
            toggle_running()   # lower half: start / stop the grinder
    _touch_was_down = active


# --------------------------------------------------------------- round display
# The GC9A01 is a 240x240 CIRCULAR panel: only the middle rows are full-width.
# Every label is horizontally centered (anchor_point x=0.5) and clustered near
# the vertical middle so nothing is clipped by the round bezel.
display = board.DISPLAY
CX = display.width // 2
CY = display.height // 2

# Solid black backdrop so the console text underneath doesn't show through.
_bg_bitmap = displayio.Bitmap(display.width, display.height, 1)
_bg_palette = displayio.Palette(1)
_bg_palette[0] = 0x000000
_background = displayio.TileGrid(_bg_bitmap, pixel_shader=_bg_palette)

# Curved title: each character is its own label placed on an arc concentric
# with the round bezel, so "GRIND BY WEIGHT" follows the top contour.  The
# terminalio font can't tilt to the tangent, so letters stay upright on the
# curve.  Smaller ARC_RADIUS -> lower and more curved; larger -> higher/flatter.
TITLE_TEXT = "GRIND BY WEIGHT"
TITLE_SCALE = 2
TITLE_COLOR = 0xFFA500
ARC_RADIUS = 106
CHAR_ADV = 6 * TITLE_SCALE + 5  # per-char arc spacing; extra gap so the ends,
                                # where the curve steepens, don't run together


def build_arc_title():
    """Return a Group of per-character labels arranged along a top arc."""
    grp = displayio.Group()
    n = len(TITLE_TEXT)
    step = CHAR_ADV / ARC_RADIUS            # angular spacing per character (rad)
    top = -math.pi / 2                      # straight up (screen y grows down)
    for i, ch in enumerate(TITLE_TEXT):
        theta = top + (i - (n - 1) / 2) * step
        x = CX + ARC_RADIUS * math.cos(theta)
        y = CY + ARC_RADIUS * math.sin(theta)
        grp.append(label.Label(
            terminalio.FONT, text=ch, scale=TITLE_SCALE, color=TITLE_COLOR,
            anchor_point=(0.5, 0.5), anchored_position=(int(x), int(y))))
    return grp


title_group = build_arc_title()

# Two touch zones split at the vertical middle (CY):
#   UPPER = arced title + live measured weight   -> tap anywhere to tare
#   LOWER = target set point + START/STOP button -> tap anywhere to start/stop
# A faint divider line marks the boundary between the two regions.
_line_palette = displayio.Palette(1)
_line_palette[0] = 0x404040
_divider = Rectangle(pixel_shader=_line_palette, width=display.width, height=2,
                     x=0, y=CY - 1)

# Upper zone: the live measured weight (the value you watch while grinding).
weight_lbl = label.Label(terminalio.FONT, text="", scale=3, color=0xFFFFFF,
                         anchor_point=(0.5, 0.5), anchored_position=(CX, 96))

# Lower zone: the target set point (number only) and the START/STOP indicator.
setpoint_lbl = label.Label(terminalio.FONT, text="", scale=3, color=0xFFA500,
                           anchor_point=(0.5, 0.5), anchored_position=(CX, 152))
startstop_lbl = label.Label(terminalio.FONT, text="", scale=2, color=0xFFFFFF,
                            anchor_point=(0.5, 0.5), anchored_position=(CX, 196))

_group = displayio.Group()
_group.append(_background)
_group.append(_divider)
_group.append(title_group)
_group.append(weight_lbl)
_group.append(setpoint_lbl)
_group.append(startstop_lbl)
display.root_group = _group


def draw_values(target, grams, running_state):
    """Refresh measured weight (upper) and set point + START/STOP (lower)."""
    weight_lbl.text = "{:.1f} g".format(grams)
    setpoint_lbl.text = "{:.1f} g".format(target)
    # The indicator shows the action a tap will take: STOP while running (red),
    # START while idle (green).
    startstop_lbl.text = "STOP" if running_state else "START"
    startstop_lbl.color = 0xFF3030 if running_state else 0x00FF00


# --------------------------------------------------------------- initial paint
draw_values(set_point, weight, running)
last_tick = time.monotonic()

# --------------------------------------------------------------- control loop
while True:
    # Keep the dial responsive and the sample window fresh every pass.
    update_setpoint()
    poll_scale()
    check_touch()

    now = time.monotonic()
    if now - last_tick >= DECISION_PERIOD:
        last_tick = now

        # Median-filter the current window, then apply the output: engaged only
        # while STARTed and still under target (STOP or reaching target cuts it).
        weight = filtered_weight()
        apply_output()

        draw_values(set_point, weight, running)

    time.sleep(0.005)
