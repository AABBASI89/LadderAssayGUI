# arduino_monitor.py

import threading
import time
import traceback

from PyQt5.QtCore import (
    QThread,
    pyqtSignal
)

import inspect

import pyfirmata
from pyfirmata import Arduino, util

# pyfirmata 1.1.0 calls inspect.getargspec, which was removed in
# Python 3.11. getfullargspec()[0] is the same list of argument names.
if not hasattr(inspect, "getargspec"):
    inspect.getargspec = inspect.getfullargspec

from config import (
    ARDUINO_PORT,
    SENSOR_START_PIN,
    SENSOR_STOP_PIN,
    EMITTER_START_PIN,
    EMITTER_STOP_PIN,
    SENSOR_POLL_SECONDS,
    START_THRESHOLD,
    STOP_THRESHOLD,
    BEAM_HYSTERESIS,
    BEAM_BROKEN_WHEN_HIGH,
    BEAM_CLEAR_HOLD_SECONDS,
    DEBOUNCE_SECONDS
)


class _SafeIterator(threading.Thread):
    """
    Replacement for pyfirmata's util.Iterator that can be stopped
    cleanly. The original keeps reading while board.exit() closes the
    serial port, which raised an uncaught exception (and a fatal
    interpreter error) at shutdown.
    """

    def __init__(self, board):

        super().__init__(daemon=True)

        self.board = board

        self._stop_event = threading.Event()

    def stop(self):

        self._stop_event.set()

        self.join(1.0)

    def run(self):

        while not self._stop_event.is_set():

            try:

                while (
                    not self._stop_event.is_set()
                    and self.board.bytes_available()
                ):
                    self.board.iterate()

                time.sleep(0.001)

            except Exception:

                # Port closed or board gone
                break


class BeamState:
    """
    Turns raw voltages into a stable broken / clear state.

    - Polarity comes from BEAM_BROKEN_WHEN_HIGH.
    - Hysteresis: after a break the voltage must move BEAM_HYSTERESIS
      back past the threshold before it can count as clear.
    - Clear hold: it must then stay clear for BEAM_CLEAR_HOLD_SECONDS,
      so flicker while the beam is blocked does not look like a series
      of clear -> broken edges.
    """

    def __init__(self, threshold):

        self.threshold = threshold

        self.broken = False

        self._clear_since = None

    def update(self, voltage, now):

        if BEAM_BROKEN_WHEN_HIGH:

            raw_broken = voltage > self.threshold

            raw_clear = voltage < self.threshold - BEAM_HYSTERESIS

        else:

            raw_broken = voltage < self.threshold

            raw_clear = voltage > self.threshold + BEAM_HYSTERESIS

        if not self.broken:

            if raw_broken:
                self.broken = True

            return self.broken

        # Currently broken: only a sustained clear reading releases it
        if raw_clear:

            if self._clear_since is None:
                self._clear_since = now

            elif now - self._clear_since >= BEAM_CLEAR_HOLD_SECONDS:

                self.broken = False

                self._clear_since = None

        else:

            self._clear_since = None

        return self.broken


class ArduinoMonitor(QThread):

    # -------------------------------------------
    # Signals
    # -------------------------------------------

    sensor_update = pyqtSignal(float, float)

    # (beam number 1 or 2, sensor voltage at the moment of the break).
    # Either beam can start or stop a trial; the GUI decides which.
    beam_broken = pyqtSignal(int, float)

    status_signal = pyqtSignal(str)

    error_signal = pyqtSignal(str)

    warning_signal = pyqtSignal(str)

    # True when the emitter LEDs have just been turned on, False for off
    emitters_changed = pyqtSignal(bool)

    # -------------------------------------------
    # Init
    # -------------------------------------------

    def __init__(
            self,
            logger=None):

        super().__init__()

        self.logger = logger

        self._stop_event = threading.Event()

        # True once the board is connected and sensors are reporting
        self.ready = False

        self.armed = False

        self.emitters_on = False

        self.board = None

        self.sensor1 = None
        self.sensor2 = None

        self.emitter1 = None
        self.emitter2 = None

        self.prev_beam1_broken = False
        self.prev_beam2_broken = False

        self.beam1_state = BeamState(START_THRESHOLD)
        self.beam2_state = BeamState(STOP_THRESHOLD)
        
        self.last_beam1_trigger = 0
        self.last_beam2_trigger = 0
        self.debounce_seconds = DEBOUNCE_SECONDS
        self.latest_sensor1 = 0.0
        self.latest_sensor2 = 0.0

    # -------------------------------------------
    # Arduino Setup
    # -------------------------------------------

    def initialize(self):

        self.board = Arduino(
            ARDUINO_PORT
        )

        self.iterator = _SafeIterator(
            self.board
        )

        # Daemon so the reader thread cannot keep the app alive on exit
        self.iterator.daemon = True

        self.iterator.start()

        # Report analog values every 1 ms (pyfirmata default is 19 ms)
        self.board.send_sysex(
            pyfirmata.SAMPLING_INTERVAL,
            util.to_two_bytes(1)
        )

        # -------------------------------
        # Emitters
        # -------------------------------

        self.emitter1 = self.board.get_pin(
            f'd:{EMITTER_START_PIN}:o'
        )

        self.emitter2 = self.board.get_pin(
            f'd:{EMITTER_STOP_PIN}:o'
        )

        # -------------------------------
        # Sensors
        # -------------------------------

        self.sensor1 = self.board.analog[SENSOR_START_PIN]
        self.sensor2 = self.board.analog[SENSOR_STOP_PIN]

        self.sensor1.enable_reporting()
        self.sensor2.enable_reporting()

        # Emitters start OFF; the GUI button turns them on
        self.emitter1.write(0)
        self.emitter2.write(0)

        self.emitters_on = False

        # Let the emitters stabilise before reading the sensors
        time.sleep(1)

        self.ready = True

        self.status_signal.emit(
            "Arduino Connected"
        )

    # -------------------------------------------
    # Armed Control
    # -------------------------------------------

    def arm(self):

        self.armed = True

        self.status_signal.emit(
            "System Armed"
        )

    def disarm(self):

        self.armed = False

        self.status_signal.emit(
            "System Disarmed"
        )

    # -------------------------------------------
    # Emitter Control
    # -------------------------------------------

    def set_emitters(self, on):
        """Turns both emitter LEDs on or off. Returns True on success."""

        if not self.ready:
            return False

        if not on:
            # With the emitters off both beams read "broken", so never
            # leave the system armed
            self.armed = False

        try:

            self.emitter1.write(1 if on else 0)
            self.emitter2.write(1 if on else 0)

        except Exception:

            self.error_signal.emit(
                traceback.format_exc()
            )

            return False

        self.emitters_on = bool(on)

        self.emitters_changed.emit(self.emitters_on)

        return True

    # -------------------------------------------
    # Read Sensor Safely
    # -------------------------------------------

    def read_voltage(self, pin):

        value = pin.read()

        if value is None:
            return None

        try:
            voltage = value * 5.0
        except Exception:
            return None

        # pyfirmata occasionally decodes a corrupted serial message into
        # a nonsense reading (seen: ~140 V). A 10-bit ADC on a 5 V board
        # can only give 0-5 V, so anything else is dropped; the sample
        # is skipped like a missing one and never reaches the beam logic.
        if not 0.0 <= voltage <= 5.0:
            return None

        return voltage

    # -------------------------------------------
    # Main Thread
    # -------------------------------------------

    def run(self):

        try:

            self.initialize()

            last_data = time.monotonic()

            no_data_warned = False

            while not self._stop_event.is_set():

                sensor1 = self.read_voltage(
                    self.sensor1
                )

                sensor2 = self.read_voltage(
                    self.sensor2
                )

                if sensor1 is None or sensor2 is None:

                    # Opening the port succeeds even if the board is not
                    # running StandardFirmata, so detect silence here
                    if (
                        not no_data_warned
                        and time.monotonic() - last_data > 3.0
                    ):

                        no_data_warned = True

                        self.warning_signal.emit(
                            "No analog data from the Arduino on "
                            f"A{SENSOR_START_PIN}/A{SENSOR_STOP_PIN}. "
                            "Check that StandardFirmata is uploaded "
                            "and that COM port is correct."
                        )

                    time.sleep(SENSOR_POLL_SECONDS)
                    continue

                last_data = time.monotonic()

                no_data_warned = False

                self.latest_sensor1 = sensor1
                self.latest_sensor2 = sensor2
                    
                # --------------------------------
                # GUI update
                # --------------------------------

                self.sensor_update.emit(
                    sensor1,
                    sensor2
                )

                # --------------------------------
                # Continuous logging
                # --------------------------------

                if self.logger:

                    self.logger.log_sensor(
                        sensor1,
                        sensor2
                    )

                # --------------------------------
                # Edge detect
                # --------------------------------
                
                now_mono = time.monotonic()

                beam1_broken_now = self.beam1_state.update(
                    sensor1,
                    now_mono
                )

                beam2_broken_now = self.beam2_state.update(
                    sensor2,
                    now_mono
                )

                beam1_trigger = (
                    not self.prev_beam1_broken
                    and
                    beam1_broken_now
                )

                beam2_trigger = (
                    not self.prev_beam2_broken
                    and
                    beam2_broken_now
                )

                # --------------------------------
                # Beam break triggers (either beam may start or stop)
                # --------------------------------

                if self.armed and beam1_trigger:

                    now = time.time()

                    if (
                        now - self.last_beam1_trigger
                        >
                        self.debounce_seconds
                    ):

                        self.last_beam1_trigger = now

                        if self.logger:

                            self.logger.log_event(
                                event="Beam1Broken",
                                sensor1=sensor1,
                                sensor2=sensor2
                            )

                        self.beam_broken.emit(1, sensor1)

                if self.armed and beam2_trigger:

                    now = time.time()

                    if (
                        now - self.last_beam2_trigger
                        >
                        self.debounce_seconds
                    ):

                        self.last_beam2_trigger = now

                        if self.logger:

                            self.logger.log_event(
                                event="Beam2Broken",
                                sensor1=sensor1,
                                sensor2=sensor2
                            )

                        self.beam_broken.emit(2, sensor2)

                # --------------------------------
                # Save states
                # --------------------------------

                self.prev_beam1_broken = beam1_broken_now
                self.prev_beam2_broken = beam2_broken_now

                time.sleep(
                    SENSOR_POLL_SECONDS
                )

        except Exception:

            self.error_signal.emit(
                traceback.format_exc()
            )
    # -------------------------------------------
    # Shutdown
    # -------------------------------------------

    def stop(self):

        # Let the polling thread finish before touching the board
        self._stop_event.set()

        self.wait(3000)

        self.ready = False

        try:

            if self.emitter1:
                self.emitter1.write(0)

            if self.emitter2:
                self.emitter2.write(0)

        except Exception:
            pass

        # Stop the reader before the serial port is closed
        try:

            if getattr(self, "iterator", None):
                self.iterator.stop()

        except Exception:
            pass

        try:

            if self.board:
                self.board.exit()

        except Exception:
            pass

        self.status_signal.emit(
            "Arduino Disconnected"
        )