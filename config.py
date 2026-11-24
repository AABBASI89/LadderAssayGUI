# config.py

from pathlib import Path

# ==========================================================
# Camera Settings
# ==========================================================

CAMERA_FPS = 150

# acA1920-155um full sensor size (used for metadata / empty-buffer
# fallback; recordings use the real frame size)
CAMERA_WIDTH = 1936
CAMERA_HEIGHT = 1216

NUM_CAMERAS = 2

# Exposure must be shorter than one frame period (1/150 s = 6.67 ms).
# It is clamped to 90% of the frame period at startup.
CAMERA_EXPOSURE_US = 4000

# Driver-side buffers per camera (OneByOne grabbing)
CAMERA_MAX_BUFFERS = 300

# ==========================================================
# Buffer Settings
# ==========================================================

PRETRIGGER_SECONDS = 1

PRETRIGGER_FRAMES = int(
    CAMERA_FPS * PRETRIGGER_SECONDS
)

# ==========================================================
# Recording Settings
# ==========================================================

# "RAW" = uncompressed, lossless AVI (about 2.3 MB per mono frame, i.e.
# ~350 MB/s per camera at 150 fps). Any 4-character OpenCV fourcc such
# as "MJPG" also works and gives much smaller (lossy) files.
VIDEO_CODEC = "RAW"

VIDEO_EXTENSION = ".avi"

# ==========================================================
# Arduino Settings
# ==========================================================

ARDUINO_PORT = "COM4"

# Beam emitters
EMITTER_START_PIN = 4   # D4
EMITTER_STOP_PIN  = 3   # D3

# Beam sensors
SENSOR_START_PIN = 0    # A0
SENSOR_STOP_PIN  = 1    # A1

# Beam detection thresholds
#
# The receivers read ~5 V with the emitters on and the beam clear, and
# drop (to ~1 V with the emitters off / beam fully blocked) when the
# beam is broken. A beam counts as broken when its voltage falls BELOW
# the threshold. These are the startup values: both can be changed
# while the program runs from the main window.
BEAM_BROKEN_WHEN_HIGH = False

# Measured with the 1 MOhm load resistors on the breadboard
# (beam clear / blocked): A0 2.50 V / 0.38 V, A1 1.66 V / 0.61 V.
# Each threshold is halfway between its clear and blocked levels.
START_THRESHOLD = 1.4   # beam 1 (A0)
STOP_THRESHOLD  = 1.1   # beam 2 (A1)

# Limits of the threshold boxes in the main window
THRESHOLD_MIN = 0.5
THRESHOLD_MAX = 4.5
THRESHOLD_STEP = 0.1

# Once broken, the voltage must move this far back past the threshold
# before the beam can count as clear (prevents noise chatter).
# Clear level = threshold + hysteresis, so it must stay below the
# lowest clear voltage (A1 reads ~1.5 V when the other beam is blocked).
BEAM_HYSTERESIS = 0.2

# ...and it must stay clear this long. The flicker while the beam is
# blocked would otherwise look like repeated clear/broken edges.
BEAM_CLEAR_HOLD_SECONDS = 0.05


def is_broken(voltage, threshold):
    """Plain threshold test used for display (no hysteresis)."""

    if BEAM_BROKEN_WHEN_HIGH:
        return voltage > threshold

    return voltage < threshold

# Minimum time between two triggers from the same beam
DEBOUNCE_SECONDS = 0.1

# Polling interval
SENSOR_POLL_SECONDS = 0.005

# ==========================================================
# Crossing Settings
# ==========================================================

# Full crossings (start beam != stop beam) needed in each direction.
# The session ends when both directions have reached this number.
# Half crossings (same beam starts and stops a trial) are logged but
# never counted.
FULL_CROSSINGS_PER_DIRECTION = 20

# ==========================================================
# Plot Settings
# ==========================================================

# Samples kept per trace, and the width of the scrolling window.
# At the ~200 Hz poll rate, 2000 samples is about 10 s.
PLOT_HISTORY = 2000

PLOT_SECONDS = 10

# Top of the voltage axis (the beam signals currently span ~0-3 V)
PLOT_Y_MAX = 3.5

PLOT_REFRESH_MS = 50

# ==========================================================
# Session Settings
# ==========================================================

ROOT_FOLDER = Path.cwd()

SESSION_ROOT = ROOT_FOLDER / "sessions"

SESSION_ROOT.mkdir(
    parents=True,
    exist_ok=True
)

# ==========================================================
# GUI
# ==========================================================

PREVIEW_FPS = 15

STATUS_IDLE = "IDLE"

STATUS_PREVIEW = "PREVIEW"

STATUS_ARMED = "ARMED"

STATUS_RECORDING = "RECORDING"