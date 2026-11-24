# gui.py

import cv2
import numpy as np

from PyQt5.QtCore import Qt
from PyQt5.QtGui import (
    QImage,
    QPixmap
)

from PyQt5.QtWidgets import (
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QMessageBox,
    QGroupBox,
    QDoubleSpinBox,
    QSpinBox,
    QLineEdit,
    QFileDialog
)

from config import (
    SESSION_BASE_FOLDER,
    SESSION_ROOT,
    CAMERA1_EXPOSURE_US,
    CAMERA2_EXPOSURE_US,
    EXPOSURE_MIN_US,
    EXPOSURE_MAX_US,
    CAMERA_FPS,
    FPS_MIN,
    FPS_MAX,
    max_exposure_us,
    sessions_root,
    save_settings,
    STATUS_IDLE,
    STATUS_PREVIEW,
    STATUS_ARMED,
    STATUS_RECORDING,
    START_THRESHOLD,
    STOP_THRESHOLD,
    THRESHOLD_MIN,
    THRESHOLD_MAX,
    THRESHOLD_STEP,
    is_broken
)

from camera_manager import CameraManager
from recorder import Recorder
from arduino_monitor import ArduinoMonitor
from sensor_plot import SensorPlotWindow
from session_logger import SessionLogger
from crossing_tracker import CrossingTracker


class MainWindow(QWidget):

    def __init__(self):

        super().__init__()
        self.setWindowTitle(
            "Ladder Assay Recorder"
        )
        self.resize(1500, 900)

        # -----------------------------------
        # State
        # -----------------------------------
        self.status = STATUS_IDLE
        self.recording_active = False
        self.current_trial = 0 # may have to remove this line
        self.beam1_count = 0
        self.beam2_count = 0
        self.initialized = False
        self.sensor_window = None
        self.latest_sensor1 = 0.0
        self.latest_sensor2 = 0.0
        self.tracker = CrossingTracker()

        # -----------------------------------
        # Logging
        # -----------------------------------
        self.session_base_folder = SESSION_BASE_FOLDER
        self.logger = SessionLogger(SESSION_ROOT)

        # -----------------------------------
        # Recorder
        # -----------------------------------
        self.recorder = Recorder(
            self.logger
        )

        # -----------------------------------
        # Camera Thread
        # -----------------------------------
        self.camera_manager = CameraManager()
        self.camera_manager.camera1_connected.connect(
        self.set_camera1_connected
        )
        self.camera_manager.camera2_connected.connect(
            self.set_camera2_connected
        )
        self.camera_manager.camera1_disconnected.connect(
            self.set_camera1_disconnected
        )
        self.camera_manager.camera2_disconnected.connect(
            self.set_camera2_disconnected
        )
        self.camera_manager.frame1_ready.connect(
            self.update_camera1
        )
        self.camera_manager.frame2_ready.connect(
            self.update_camera2
        )
        self.camera_manager.status_signal.connect(
            self.handle_camera_status
        )
        self.camera_manager.error_signal.connect(
            self.handle_camera_error
        )
        self.camera_manager.info_signal.connect(
            self.show_info
        )
        
        # -----------------------------------
        # Arduino Thread
        # -----------------------------------
        self.arduino = ArduinoMonitor(
            logger=self.logger
        )
        self.arduino.sensor_update.connect(
            self.sensor_update
        )

        self.arduino.status_signal.connect(
            self.handle_arduino_status
        )

        self.arduino.error_signal.connect(
            self.handle_arduino_error
        )

        self.arduino.warning_signal.connect(
            self.show_error
        )

        self.arduino.emitters_changed.connect(
            self.handle_emitters_changed
        )

        self.arduino.beam_broken.connect(
            self.handle_beam_broken
        )

        # -----------------------------------
        # UI
        # -----------------------------------
        self.build_ui()
        self.update_status(
            STATUS_IDLE
        )

        # -----------------------------------
        # Start Threads
        # -----------------------------------
        self.camera_manager.start()
        self.arduino.start()

    # ==================================================
    # UI
    # ==================================================

    def build_ui(self):

        layout = QVBoxLayout(self)

        # ----------------------------
        # Camera Previews
        # ----------------------------
        camera_layout = QHBoxLayout()
        self.cam1_label = QLabel(
            "Camera 1"
        )
        self.cam2_label = QLabel(
            "Camera 2"
        )
        self.cam1_label.setFixedSize(
            640,
            400
        )
        self.cam2_label.setFixedSize(
            640,
            400
        )
        self.cam1_label.setStyleSheet(
            "background:black;"
        )
        self.cam2_label.setStyleSheet(
            "background:black;"
        )
        camera_layout.addWidget(
            self.cam1_label
        )
        camera_layout.addWidget(
            self.cam2_label
        )
        
        # -----------------------------------
        # Hardware Status
        # -----------------------------------

        hardware_group = QGroupBox("Hardware Status")

        hardware_grid = QGridLayout()

        self.arduino_hw = QLabel("● Disconnected")
        self.camera1_hw = QLabel("● Disconnected")
        self.camera2_hw = QLabel("● Disconnected")

        self.arduino_hw.setStyleSheet(
            "color:red;font-weight:bold;"
        )

        self.camera1_hw.setStyleSheet(
            "color:red;font-weight:bold;"
        )

        self.camera2_hw.setStyleSheet(
            "color:red;font-weight:bold;"
        )

        hardware_grid.addWidget(
            QLabel("Arduino"),
            0, 0
        )

        hardware_grid.addWidget(
            self.arduino_hw,
            0, 1
        )

        hardware_grid.addWidget(
            QLabel("Camera 1"),
            1, 0
        )

        hardware_grid.addWidget(
            self.camera1_hw,
            1, 1
        )

        hardware_grid.addWidget(
            QLabel("Camera 2"),
            2, 0
        )

        hardware_grid.addWidget(
            self.camera2_hw,
            2, 1
        )

        hardware_group.setLayout(
            hardware_grid
        )

        # ----------------------------
        # Status Panel
        # ----------------------------

        status_group = QGroupBox(
            "System Status"
        )
        grid = QGridLayout()
        self.status_label = QLabel()
        self.trial_label = QLabel(
            "0"
        )
        self.beam1_label = QLabel(
            "0"
        )
        self.beam2_label = QLabel(
            "0"
        )
        self.sensor1_label = QLabel(
            "UNKNOWN"
        )
        self.sensor2_label = QLabel(
            "UNKNOWN"
        )
        self.session_label = QLabel(
            str(
                self.logger.get_session_folder()
            )
        )
        grid.addWidget(
            QLabel("Status"),
            0, 0
        )
        grid.addWidget(
            self.status_label,
            0, 1
        )
        grid.addWidget(
            QLabel("Current Trial"),
            1, 0
        )
        grid.addWidget(
            self.trial_label,
            1, 1
        )
        grid.addWidget(
            QLabel("Beam1 Breaks"),
            2, 0
        )
        grid.addWidget(
            self.beam1_label,
            2, 1
        )
        grid.addWidget(
            QLabel("Beam2 Breaks"),
            3, 0
        )
        grid.addWidget(
            self.beam2_label,
            3, 1
        )
        grid.addWidget(
            QLabel("Start Beam (A0)"),
            4, 0
        )
        grid.addWidget(
            self.sensor1_label,
            4, 1
        )
        grid.addWidget(
            QLabel("Stop Beam (A1)"),
            5, 0
        )
        grid.addWidget(
            self.sensor2_label,
            5, 1
        )
        self.next_beam_label = QLabel("Either")
        self.full_label = QLabel()
        self.half_label = QLabel("0")
        grid.addWidget(
            QLabel("Next start beam"),
            6, 0
        )
        grid.addWidget(
            self.next_beam_label,
            6, 1
        )
        grid.addWidget(
            QLabel("Full crossings"),
            7, 0
        )
        grid.addWidget(
            self.full_label,
            7, 1
        )
        grid.addWidget(
            QLabel("Half crossings (not counted)"),
            8, 0
        )
        grid.addWidget(
            self.half_label,
            8, 1
        )
        grid.addWidget(
            QLabel("Session"),
            9, 0
        )
        grid.addWidget(
            self.session_label,
            9, 1
        )
        self.update_crossing_labels()
        status_group.setLayout(grid)

        # ----------------------------
        # Beam thresholds (editable while running)
        # ----------------------------
        threshold_group = QGroupBox(
            "Beam break thresholds - a beam is broken when its "
            "voltage falls below the value"
        )
        threshold_layout = QHBoxLayout()

        self.threshold1_spin = self.make_threshold_spin(
            START_THRESHOLD
        )
        self.threshold2_spin = self.make_threshold_spin(
            STOP_THRESHOLD
        )
        self.threshold1_spin.valueChanged.connect(
            lambda value: self.threshold_changed(1, value)
        )
        self.threshold2_spin.valueChanged.connect(
            lambda value: self.threshold_changed(2, value)
        )

        threshold_layout.addWidget(
            QLabel("Beam 1 (A0)")
        )
        threshold_layout.addWidget(
            self.threshold1_spin
        )
        threshold_layout.addSpacing(30)
        threshold_layout.addWidget(
            QLabel("Beam 2 (A1)")
        )
        threshold_layout.addWidget(
            self.threshold2_spin
        )
        threshold_layout.addStretch()
        threshold_group.setLayout(threshold_layout)

        # ----------------------------
        # Camera exposure (editable during preview)
        # ----------------------------
        exposure_group = QGroupBox(
            "Camera exposure and frame rate (applied immediately, "
            "saved for next launch)"
        )
        exposure_layout = QHBoxLayout()

        self.exposure1_spin = self.make_exposure_spin(
            CAMERA1_EXPOSURE_US
        )
        self.exposure2_spin = self.make_exposure_spin(
            CAMERA2_EXPOSURE_US
        )
        self.exposure1_spin.valueChanged.connect(
            lambda value: self.exposure_changed(0, value)
        )
        self.exposure2_spin.valueChanged.connect(
            lambda value: self.exposure_changed(1, value)
        )

        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(FPS_MIN, FPS_MAX)
        self.fps_spin.setSuffix(" fps")
        self.fps_spin.setValue(CAMERA_FPS)
        self.fps_spin.setToolTip(
            "Exposure is limited to 90% of the frame period "
            "(7500 us needs 120 fps or less). Cannot be changed "
            "while recording."
        )
        self.update_exposure_limit()
        self.fps_spin.valueChanged.connect(
            self.fps_changed
        )

        exposure_layout.addWidget(QLabel("Camera 1"))
        exposure_layout.addWidget(self.exposure1_spin)
        exposure_layout.addSpacing(30)
        exposure_layout.addWidget(QLabel("Camera 2"))
        exposure_layout.addWidget(self.exposure2_spin)
        exposure_layout.addSpacing(30)
        exposure_layout.addWidget(QLabel("Frame rate"))
        exposure_layout.addWidget(self.fps_spin)
        exposure_layout.addStretch()
        exposure_group.setLayout(exposure_layout)

        # ----------------------------
        # Save location
        # ----------------------------
        folder_group = QGroupBox(
            "Save location (a 'sessions' folder is created inside it)"
        )
        folder_layout = QHBoxLayout()

        self.folder_edit = QLineEdit(
            str(self.session_base_folder)
        )
        self.folder_edit.setReadOnly(True)

        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(
            self.browse_folder
        )

        folder_layout.addWidget(self.folder_edit)
        folder_layout.addWidget(self.browse_button)
        folder_group.setLayout(folder_layout)

        # Last hardware error / warning (full text in tooltip and log)
        self.error_label = QLabel("")
        self.error_label.setStyleSheet(
            "color:red;font-weight:bold;"
        )
        self.error_label.setWordWrap(True)

        # ----------------------------
        # Buttons
        # ----------------------------
        button_layout = QHBoxLayout()
        self.preview_button = QPushButton(
            "Preview"
        )
        self.arm_button = QPushButton(
            "Start Armed"
        )
        self.stop_button = QPushButton(
            "Stop"
        )
        self.sensor_button = QPushButton(
            "Test Sensors"
        )
        self.emitter_button = QPushButton(
            "Turn emitters on"
        )
        self.emitter_button.clicked.connect(
            self.toggle_emitters
        )
        self.preview_button.clicked.connect(
            self.preview_clicked
        )
        self.arm_button.clicked.connect(
            self.arm_clicked
        )
        self.stop_button.clicked.connect(
            self.stop_clicked
        )
        self.sensor_button.clicked.connect(
            self.show_sensor_plot
        )
        button_layout.addWidget(
            self.preview_button
        )
        button_layout.addWidget(
            self.arm_button
        )
        button_layout.addWidget(
            self.stop_button
        )
        button_layout.addWidget(
            self.sensor_button
        )
        button_layout.addWidget(
            self.emitter_button
        )

        # ----------------------------
        # Layout
        # ----------------------------
        layout.addLayout(camera_layout)
        layout.addWidget(status_group)
        layout.addWidget(threshold_group)
        layout.addWidget(exposure_group)
        layout.addWidget(folder_group)
        layout.addWidget(self.error_label)
        layout.addLayout(button_layout)
        layout.addWidget(hardware_group)

    @staticmethod
    def make_threshold_spin(value):

        spin = QDoubleSpinBox()

        spin.setRange(
            THRESHOLD_MIN,
            THRESHOLD_MAX
        )

        spin.setSingleStep(
            THRESHOLD_STEP
        )

        spin.setDecimals(2)

        spin.setSuffix(" V")

        spin.setValue(value)

        return spin

    @staticmethod
    def make_exposure_spin(value):

        spin = QSpinBox()

        spin.setRange(
            EXPOSURE_MIN_US,
            EXPOSURE_MAX_US
        )

        spin.setSingleStep(100)

        spin.setSuffix(" µs")

        spin.setValue(value)

        return spin

    # ==================================================
    # Exposure
    # ==================================================

    def exposure_changed(self, index, value):
        """Applies the new exposure to the running camera and saves it
        in the settings file."""

        self.camera_manager.set_exposure(index, value)

        save_settings(**{f"cam{index + 1}_exposure_us": value})

        self.logger.log_event(
            "ExposureChanged",
            details=f"Camera{index + 1} exposure = {value} us"
        )

    def update_exposure_limit(self):
        """Exposure can be at most 90% of the frame period."""

        limit = max_exposure_us(self.fps_spin.value())

        # Signals blocked so that a value clamped by the new limit is
        # not written over the saved setting; the camera applies the
        # same limit itself.
        for spin in (self.exposure1_spin, self.exposure2_spin):

            spin.blockSignals(True)
            spin.setMaximum(limit)
            spin.blockSignals(False)

    def fps_changed(self, value):

        if self.recording_active:

            # Video files use one rate; put the spin back
            self.fps_spin.blockSignals(True)
            self.fps_spin.setValue(self.camera_manager.fps)
            self.fps_spin.blockSignals(False)

            self.show_info(
                "Frame rate cannot be changed while recording."
            )

            return

        self.update_exposure_limit()

        self.camera_manager.set_fps(value)

        save_settings(camera_fps=value)

        self.logger.log_event(
            "FpsChanged",
            details=f"Frame rate = {value} fps"
        )

    # ==================================================
    # Save location
    # ==================================================

    def browse_folder(self):
        """Lets the user pick where the 'sessions' folder lives. A new
        session is started there (counts and crossings restart)."""

        if (
            self.recording_active
            or self.status == STATUS_ARMED
        ):

            QMessageBox.warning(
                self,
                "Save location",
                "Stop recording before changing the save location."
            )

            return

        folder = QFileDialog.getExistingDirectory(
            self,
            "Select folder for the sessions folder",
            str(self.session_base_folder)
        )

        if not folder:
            return

        try:

            root = sessions_root(folder)

            self.logger.change_root(root)

        except OSError as e:

            self.show_error(
                f"Could not use folder {folder}: {e}"
            )

            return

        self.session_base_folder = folder

        self.folder_edit.setText(folder)

        save_settings(session_base_folder=folder)

        # New session: restart the per-session counters
        self.tracker = CrossingTracker()
        self.beam1_count = 0
        self.beam2_count = 0
        self.beam1_label.setText("0")
        self.beam2_label.setText("0")
        self.trial_label.setText("0")
        self.update_crossing_labels()

        self.session_label.setText(
            str(self.logger.get_session_folder())
        )

    # ==================================================
    # Status
    # ==================================================

    def update_status(
            self,
            status
    ):

        self.status = status

        self.status_label.setText(
            status
        )

        # Armed / stop can also end the preview, so follow its real state
        self.preview_button.setText(
            "Stop Preview"
            if self.camera_manager.preview_enabled
            else "Preview"
        )

    def set_camera1_connected(self):

        self.camera1_hw.setText(
            "● Connected"
        )

        self.camera1_hw.setStyleSheet(
            "color:green;font-weight:bold;"
        )

    def set_camera2_connected(self):

        self.camera2_hw.setText(
            "● Connected"
        )

        self.camera2_hw.setStyleSheet(
            "color:green;font-weight:bold;"
        )

    def set_camera1_disconnected(self):

        self.camera1_hw.setText(
            "● Disconnected"
        )

        self.camera1_hw.setStyleSheet(
            "color:red;font-weight:bold;"
        )

        self.show_no_camera(self.cam1_label, "Camera 1")

    def set_camera2_disconnected(self):

        self.camera2_hw.setText(
            "● Disconnected"
        )

        self.camera2_hw.setStyleSheet(
            "color:red;font-weight:bold;"
        )

        self.show_no_camera(self.cam2_label, "Camera 2")

    def show_no_camera(self, label, name, message="not connected"):
        """Placeholder in a camera's preview panel (camera absent, or
        preview stopped)."""

        label.clear()

        label.setText(f"{name}\n{message}")

        label.setAlignment(Qt.AlignCenter)

        label.setStyleSheet(
            "background:black;color:#888888;font-size:14pt;"
        )
               
    # ==================================================
    # Preview
    # ==================================================

    def preview_clicked(self):
        """Toggle: starts the preview, or stops it if it is running."""

        if self.recording_active:
            return

        if self.camera_manager.preview_enabled:

            self.stop_preview()

            return

        # Preview and armed are mutually exclusive
        self.arduino.disarm()

        self.camera_manager.enable_preview()

        self.update_status(
            STATUS_PREVIEW
        )

    def stop_preview(self):

        self.camera_manager.disable_preview()

        # Cameras that are not connected keep their own placeholder
        for i, label in enumerate(
                (self.cam1_label, self.cam2_label)
        ):

            if self.camera_manager.active[i]:

                self.show_no_camera(
                    label,
                    f"Camera {i + 1}",
                    "preview stopped"
                )

        # Also refreshes the button text
        self.update_status(
            STATUS_IDLE
            if self.status == STATUS_PREVIEW
            else self.status
        )

    # ==================================================
    # Emitters
    # ==================================================

    def toggle_emitters(self):

        if not self.arduino.ready:

            QMessageBox.warning(
                self,
                "Emitters",
                "The Arduino is not connected."
            )

            return

        turning_on = not self.arduino.emitters_on

        # Switching the emitters off makes both beams read "broken",
        # so end any armed / recording state first
        if not turning_on and (
            self.recording_active
            or self.status == STATUS_ARMED
        ):
            self.stop_clicked()

        self.arduino.set_emitters(turning_on)

    def handle_emitters_changed(self, on):

        self.emitter_button.setText(
            "Turn emitters off"
            if on
            else "Turn emitters on"
        )

        self.logger.log_event(
            "EmittersOn" if on else "EmittersOff"
        )

    # ==================================================
    # Arm
    # ==================================================

    def arm_clicked(self):

        if self.recording_active:
            return

        if not self.camera_manager.ready:

            QMessageBox.warning(
                self,
                "Cannot Arm",
                "No Basler camera is connected and grabbing."
            )

            return

        if not self.arduino.ready:

            QMessageBox.warning(
                self,
                "Cannot Arm",
                "The Arduino is not connected."
            )

            return

        if not self.arduino.emitters_on:

            QMessageBox.warning(
                self,
                "Cannot Arm",
                "Turn the emitters on before arming."
            )

            return

        if self.tracker.complete:

            QMessageBox.information(
                self,
                "Session complete",
                "This session already has all its full crossings. "
                "Restart the application for a new session."
            )

            return

        self.camera_manager.disable_preview()

        self.arduino.arm()

        self.update_status(
            STATUS_ARMED
        )

        self.logger.log_event(
            "SystemArmed"
        )

    # ==================================================
    # Manual Stop
    # ==================================================

    def stop_clicked(self):

        self.recording_active = False

        self.arduino.disarm()

        self.camera_manager.stop_recording()

        self.recorder.abort()

        self.update_status(
            STATUS_IDLE
        )

        self.logger.log_event(
            "SystemDisarmed"
        )

    # ==================================================
    # Start Trigger
    # ==================================================

    def handle_beam_broken(self, beam, voltage):

        if self.recording_active:

            # Any beam, including the one that started the trial
            self.stop_trial_on_beam(beam, voltage)

        elif self.status == STATUS_ARMED:

            self.start_trial_on_beam(beam, voltage)

    def start_trial_on_beam(self, beam, voltage):

        # Only the beam that ended the previous trial may start this one
        if not self.tracker.can_start(beam):

            self.logger.log_event(
                "BeamIgnored",
                details=(
                    f"Beam{beam} broken; waiting for "
                    f"Beam{self.tracker.next_start_beam}"
                )
            )

            return

        try:

            # Snapshots the pre-trigger buffer and starts live
            # recording atomically; encoding runs in writer threads
            self.camera_manager.start_recording(
                self.recorder,
                start_voltage=voltage
            )

        except Exception as e:

            self.camera_manager.stop_recording()

            self.show_error(
                f"Could not start recording: {e}"
            )

            return

        self.tracker.start(beam)

        self.set_beam_count(beam)

        self.recording_active = True

        self.logger.log_event(
            event="RecordingStarted",
            details=f"Started by Beam{beam}"
        )

        self.trial_label.setText(
            str(
                self.recorder.current_trial()
            )
        )

        self.update_status(
            STATUS_RECORDING
        )

    def stop_trial_on_beam(self, beam, voltage):

        self.set_beam_count(beam)

        self.camera_manager.stop_recording()

        trial = self.recorder.current_trial()

        self.recorder.stop_trial(
            stop_voltage=voltage
        )

        self.recording_active = False

        crossing = self.tracker.stop(beam)

        self.logger.log_event(
            event="RecordingStopped",
            details=(
                f"Stopped by Beam{beam}: {crossing['type']} "
                f"{crossing['direction']}"
            )
        )

        self.logger.log_crossing(
            trial,
            crossing,
            self.tracker
        )

        self.update_crossing_labels()

        if self.tracker.complete:

            self.finish_session()

            return

        self.update_status(
            STATUS_ARMED
        )

    def set_beam_count(self, beam):
        """Counts a break that started or stopped a trial."""

        if beam == 1:

            self.beam1_count += 1

            self.beam1_label.setText(
                str(self.beam1_count)
            )

        else:

            self.beam2_count += 1

            self.beam2_label.setText(
                str(self.beam2_count)
            )

    def update_crossing_labels(self):

        t = self.tracker

        self.next_beam_label.setText(
            "Either"
            if t.next_start_beam is None
            else f"Beam {t.next_start_beam}"
        )

        self.full_label.setText(
            f"{t.full_total} / {t.target_total}   "
            f"(1→2: {t.full_1_to_2} / {t.per_direction},  "
            f"2→1: {t.full_2_to_1} / {t.per_direction})"
        )

        self.half_label.setText(
            str(t.half_count)
        )

    def finish_session(self):

        t = self.tracker

        self.arduino.disarm()

        self.update_status(
            STATUS_IDLE
        )

        self.logger.log_event(
            "SessionComplete",
            details=(
                f"{t.full_total} full crossings "
                f"(1->2: {t.full_1_to_2}, 2->1: {t.full_2_to_1}), "
                f"{t.half_count} half crossings"
            )
        )

        QMessageBox.information(
            self,
            "Session complete",
            f"{t.full_total} full crossings recorded "
            f"({t.half_count} half crossings logged, not counted)."
        )

    # ==================================================
    # Errors / Camera status
    # ==================================================

    def show_info(self, message):
        """Neutral notice (e.g. a camera is not connected). Not an error:
        nothing is stopped and the buttons keep working."""

        self.error_label.setStyleSheet(
            "color:#555555;"
        )

        self.error_label.setText(message)

        self.error_label.setToolTip(message)

        self.logger.log_event(
            "INFO",
            details=message
        )

    def show_error(self, message):

        print(message)

        lines = message.strip().splitlines()

        self.error_label.setStyleSheet(
            "color:red;font-weight:bold;"
        )

        self.error_label.setText(
            lines[-1] if lines else ""
        )

        self.error_label.setToolTip(message)

        self.logger.log_event(
            "ERROR",
            details=message.replace("\n", " | ")
        )

    def handle_camera_status(self, message):

        if "dropped" in message:

            self.logger.log_event(
                "FrameDrop",
                details=message
            )

            self.error_label.setStyleSheet(
                "color:red;font-weight:bold;"
            )

            self.error_label.setText(message)

    def handle_camera_error(self, message):

        self.show_error(message)

        # A camera failure must not leave a recording open or armed
        self.stop_clicked()

    def handle_arduino_error(self, message):

        self.show_error(message)

        self.set_arduino_disconnected()

        self.stop_clicked()

    # ==================================================
    # Sensor Updates
    # ==================================================

    def sensor_update(
            self,
            sensor1,
            sensor2
    ):

        beam1_state = (
            "BROKEN"
            if is_broken(sensor1, self.threshold1_spin.value())
            else "CLEAR"
        )

        beam2_state = (
            "BROKEN"
            if is_broken(sensor2, self.threshold2_spin.value())
            else "CLEAR"
        )

        self.sensor1_label.setText(
            f"{sensor1:.2f} V ({beam1_state})"
        )

        self.sensor2_label.setText(
            f"{sensor2:.2f} V ({beam2_state})"
        )

        if self.sensor_window:

            self.sensor_window.update_sensor_values(
                sensor1,
                sensor2
            )
            
        self.latest_sensor1 = sensor1
        self.latest_sensor2 = sensor2

    # ==================================================
    # Sensor Plot
    # ==================================================

    def show_sensor_plot(self):

        if self.sensor_window is None:

            self.sensor_window = (
                SensorPlotWindow(
                    self.threshold1_spin.value(),
                    self.threshold2_spin.value()
                )
            )

        self.sensor_window.show()

    # ==================================================
    # Thresholds
    # ==================================================

    def threshold_changed(self, beam, value):
        """Applies a threshold edited in the main window right away
        (detection, status text and the plot's dashed line)."""

        state = (
            self.arduino.beam1_state
            if beam == 1
            else self.arduino.beam2_state
        )

        state.threshold = value

        if self.sensor_window is not None:

            self.sensor_window.set_threshold(beam, value)

        self.logger.log_event(
            "ThresholdChanged",
            details=f"Beam{beam} threshold = {value:.2f} V"
        )
        
    # ==================================================
    # Arduion Status
    # ==================================================    
        
    def set_arduino_connected(self):

        self.arduino_hw.setText(
            "● Connected"
        )

        self.arduino_hw.setStyleSheet(
            "color:green;font-weight:bold;"
        )


    def set_arduino_disconnected(self):

        self.arduino_hw.setText(
            "● Disconnected"
        )

        self.arduino_hw.setStyleSheet(
            "color:red;font-weight:bold;"
        )        

    def handle_arduino_status(
            self,
            message
    ):

        if "Connected" in message:

            self.set_arduino_connected()

        elif "Disconnected" in message:

            self.set_arduino_disconnected()
                             
    # ==================================================
    # Camera Display Helpers
    # ==================================================

    def convert_frame(
            self,
            frame
    ):

        # Mono cameras deliver 2-D frames
        if frame.ndim == 2:

            frame = np.ascontiguousarray(frame)

            h, w = frame.shape

            image = QImage(
                frame.data,
                w,
                h,
                w,
                QImage.Format_Grayscale8
            )

            return QPixmap.fromImage(
                image
            )

        rgb = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2RGB
        )

        h, w, ch = rgb.shape

        bytes_per_line = ch * w

        image = QImage(
            rgb.data,
            w,
            h,
            bytes_per_line,
            QImage.Format_RGB888
        )

        return QPixmap.fromImage(
            image
        )

    def update_camera1(
            self,
            frame
    ):

        # Frames still queued when the preview was stopped
        if not self.camera_manager.preview_enabled:
            return

        pix = self.convert_frame(
            frame
        )

        self.cam1_label.setPixmap(
            pix.scaled(
                self.cam1_label.width(),
                self.cam1_label.height(),
                Qt.KeepAspectRatio
            )
        )

    def update_camera2(
            self,
            frame
    ):

        if not self.camera_manager.preview_enabled:
            return

        pix = self.convert_frame(
            frame
        )

        self.cam2_label.setPixmap(
            pix.scaled(
                self.cam2_label.width(),
                self.cam2_label.height(),
                Qt.KeepAspectRatio
            )
        )

    # ==================================================
    # Shutdown
    # ==================================================

    def closeEvent(
            self,
            event
    ):

        try:

            self.arduino.disarm()

            self.camera_manager.stop_recording()

            self.recorder.abort()

            self.camera_manager.stop()

            self.arduino.stop()

            # Let the writer threads finish flushing the AVI files
            self.recorder.wait_finalize()

            self.logger.close()

            if self.sensor_window is not None:
                self.sensor_window.close()

        except Exception as e:

            QMessageBox.warning(
                self,
                "Shutdown Error",
                str(e)
            )

        event.accept()