# session_logger.py

import csv
import json
import threading
from pathlib import Path
from datetime import datetime

from config import (
    SESSION_ROOT,
    CAMERA_FPS,
    CAMERA_WIDTH,
    CAMERA_HEIGHT,
    PRETRIGGER_FRAMES,
    VIDEO_CODEC,
    START_THRESHOLD,
    STOP_THRESHOLD,
    EMITTER_START_PIN,
    EMITTER_STOP_PIN,
    SENSOR_START_PIN,
    SENSOR_STOP_PIN,
    FULL_CROSSINGS_PER_DIRECTION
)


class SessionLogger:
    """
    Handles:

    Session creation
    Trial creation
    Event logging
    Sensor logging
    Session metadata

    Folder Layout

    Session_YYYYMMDD_HHMMSS/
        events.csv
        sensor_trace.csv
        session.json

        Trial_001/
            cam1.avi
            cam2.avi
            trial_info.csv

        Trial_002/
            ...
    """

    def __init__(self):

        self.session_folder = None

        self.events_file = None
        self.sensor_file = None

        self.current_trial = 0

        # log_event is called from the GUI, Arduino and recorder threads
        self._lock = threading.RLock()

        self._sensor_handle = None
        self._sensor_writer = None
        self._sensor_rows = 0

        self.create_session()

    # ==================================================
    # Session Creation
    # ==================================================

    def create_session(self):

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        self.session_folder = (
            SESSION_ROOT /
            f"Session_{timestamp}"
        )

        self.session_folder.mkdir(
            parents=True,
            exist_ok=True
        )

        self.events_file = (
            self.session_folder /
            "events.csv"
        )

        self.sensor_file = (
            self.session_folder /
            "sensor_trace.csv"
        )

        self.crossings_file = (
            self.session_folder /
            "crossings.csv"
        )

        self._create_event_log()

        self._create_crossing_log()

        self._create_sensor_log()

        self._create_session_json()

    # ==================================================
    # Event Log
    # ==================================================

    def _create_event_log(self):

        with open(
                self.events_file,
                "w",
                newline=""
        ) as f:

            writer = csv.writer(f)

            writer.writerow([
                "Timestamp",
                "Trial",
                "Event",
                "StartBeam_V",
                "StopBeam_V",
                "Details"
            ])

    # ==================================================
    # Crossing Log
    # ==================================================

    def _create_crossing_log(self):

        with open(
                self.crossings_file,
                "w",
                newline=""
        ) as f:

            csv.writer(f).writerow([
                "Trial",
                "Timestamp",
                "StartBeam",
                "StopBeam",
                "Type",
                "Direction",
                "Counted",
                "Full_1to2",
                "Full_2to1",
                "FullTotal",
                "HalfTotal"
            ])

    def log_crossing(
            self,
            trial,
            crossing,
            tracker
    ):
        """One row per finished trial. Half crossings (and full ones past
        the quota) are written with Counted=NO."""

        with self._lock:

            with open(
                    self.crossings_file,
                    "a",
                    newline=""
            ) as f:

                csv.writer(f).writerow([
                    trial,
                    datetime.now().isoformat(),
                    crossing["start_beam"],
                    crossing["stop_beam"],
                    crossing["type"],
                    crossing["direction"],
                    "YES" if crossing["counted"] else "NO",
                    tracker.full_1_to_2,
                    tracker.full_2_to_1,
                    tracker.full_total,
                    tracker.half_count
                ])

    # ==================================================
    # Sensor Log
    # ==================================================

    def _create_sensor_log(self):

        with open(
                self.sensor_file,
                "w",
                newline=""
        ) as f:

            writer = csv.writer(f)

            writer.writerow([
                "Timestamp",
                "StartBeam_V",
                "StopBeam_V"
            ])

        # Kept open: reopening the file ~200x/s slowed the sensor loop
        self._sensor_handle = open(
            self.sensor_file,
            "a",
            newline=""
        )

        self._sensor_writer = csv.writer(
            self._sensor_handle
        )

    # ==================================================
    # Session Metadata
    # ==================================================

    def _create_session_json(self):

        metadata = {

            "created":
                datetime.now().isoformat(),

            "camera_fps":
                CAMERA_FPS,

            "resolution":
                [
                    CAMERA_WIDTH,
                    CAMERA_HEIGHT
                ],

            "pretrigger_frames":
                PRETRIGGER_FRAMES,

            "codec":
                VIDEO_CODEC,

            "start_emitter_pin":
                EMITTER_START_PIN,

            "stop_emitter_pin":
                EMITTER_STOP_PIN,

            "start_sensor_pin":
                SENSOR_START_PIN,

            "stop_sensor_pin":
                SENSOR_STOP_PIN,

            "start_threshold":
                START_THRESHOLD,

            "stop_threshold":
                STOP_THRESHOLD,

            "full_crossings_per_direction":
                FULL_CROSSINGS_PER_DIRECTION
        }

        session_json = (
            self.session_folder /
            "session.json"
        )

        with open(
                session_json,
                "w"
        ) as f:

            json.dump(
                metadata,
                f,
                indent=4
            )

    # ==================================================
    # Trial Handling
    # ==================================================

    def create_trial_folder(self):

        with self._lock:

            self.current_trial += 1

            trial_folder = (
                self.session_folder /
                f"Trial_{self.current_trial:03d}"
            )

            trial_folder.mkdir(
                parents=True,
                exist_ok=True
            )

            self.log_event(
                "TrialFolderCreated"
            )

            return trial_folder

    # ==================================================
    # Event Logging
    # ==================================================

    def log_event(
            self,
            event,
            sensor1="",
            sensor2="",
            details=""
    ):

        with self._lock:

            with open(
                    self.events_file,
                    "a",
                    newline=""
            ) as f:

                writer = csv.writer(f)

                writer.writerow([

                    datetime.now().isoformat(),

                    self.current_trial,

                    event,

                    sensor1,

                    sensor2,

                    details

                ])

    # ==================================================
    # Sensor Logging
    # ==================================================

    def log_sensor(
            self,
            sensor1,
            sensor2
    ):

        with self._lock:

            if self._sensor_writer is None:
                return

            self._sensor_writer.writerow([

                datetime.now().isoformat(),

                sensor1,

                sensor2
            ])

            self._sensor_rows += 1

            # ~0.5 s of data at the 5 ms poll rate
            if self._sensor_rows % 100 == 0:
                self._sensor_handle.flush()

    def close(self):

        with self._lock:

            if self._sensor_handle is not None:

                self._sensor_handle.close()

                self._sensor_handle = None
                self._sensor_writer = None

    # ==================================================
    # Trial Summary
    # ==================================================

    def save_trial_info(
            self,
            trial_folder,
            start_time,
            stop_time,
            frames_cam1,
            frames_cam2,
            pretrigger_frames,
            duration_seconds,
            start_trigger_voltage="",
            stop_trigger_voltage="",
            trial_number=None
    ):

        if trial_number is None:
            trial_number = self.current_trial

        trial_csv = (
            Path(trial_folder) /
            "trial_info.csv"
        )

        with open(
                trial_csv,
                "w",
                newline=""
        ) as f:

            writer = csv.writer(f)

            writer.writerow([
                "Field",
                "Value"
            ])

            writer.writerow([
                "Trial",
                trial_number
            ])

            writer.writerow([
                "StartTime",
                start_time
            ])

            writer.writerow([
                "StopTime",
                stop_time
            ])

            writer.writerow([
                "FramesCam1",
                frames_cam1
            ])

            writer.writerow([
                "FramesCam2",
                frames_cam2
            ])

            writer.writerow([
                "DurationSeconds",
                duration_seconds
            ])

            writer.writerow([
                "PretriggerFrames",
                pretrigger_frames
            ])
            
            writer.writerow([
                "StartTriggerVoltage",
                start_trigger_voltage
            ])

            writer.writerow([
                "StopTriggerVoltage",
                stop_trigger_voltage
            ])


    # ==================================================
    # Utilities
    # ==================================================

    def get_session_folder(self):

        return self.session_folder

    def get_trial_number(self):

        return self.current_trial