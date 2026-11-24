# camera_manager.py

import threading
import time
import traceback
from collections import deque

import cv2
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal
from pypylon import pylon

from config import (
    CAMERA_EXPOSURE_US,
    CAMERA_MAX_BUFFERS,
    PREVIEW_FPS
)

MAX_CAMERAS = 2


class CameraManager(QThread):
    """
    Grabs frames from up to two Basler cameras.

    Works with 0, 1 or 2 cameras connected: a missing camera is
    reported through info_signal / cameraN_disconnected (not as an
    error), and its frame is simply None in recordings.
    """

    frame1_ready = pyqtSignal(np.ndarray)
    frame2_ready = pyqtSignal(np.ndarray)

    status_signal = pyqtSignal(str)

    # Real faults (camera failed to open, stopped grabbing, ...)
    error_signal = pyqtSignal(str)

    # Normal conditions worth telling the user (e.g. no camera plugged in)
    info_signal = pyqtSignal(str)

    camera1_connected = pyqtSignal()
    camera2_connected = pyqtSignal()

    camera1_disconnected = pyqtSignal()
    camera2_disconnected = pyqtSignal()

    def __init__(
            self,
            fps=150,
            pretrigger_seconds=1):

        super().__init__()

        self._stop_event = threading.Event()

        # True once at least one camera is grabbing
        self.ready = False

        # Which of the two camera slots hold a working camera
        self.active = (False, False)

        self.preview_enabled = False

        self.recording_enabled = False

        self.recorder = None

        self.fps = fps

        self.pretrigger_seconds = pretrigger_seconds

        self.buffer_length = int(
            fps * pretrigger_seconds
        )

        self.buffers = [
            deque(maxlen=self.buffer_length),
            deque(maxlen=self.buffer_length)
        ]

        # Protects the buffers and the recording flag so that the
        # pre-trigger snapshot and live frames are contiguous
        self.buffer_lock = threading.Lock()

        self.frame_counts = [0, 0]

        self.dropped = [0, 0]

        self.cams = [None, None]

        self.converters = [None, None]

        self.native_mono8 = [False, False]

    # --------------------------------------------------
    # Camera Initialization
    # --------------------------------------------------

    def initialize_cameras(self):
        """Returns True if at least one camera is grabbing."""

        tl_factory = pylon.TlFactory.GetInstance()

        devices = tl_factory.EnumerateDevices()

        count = min(len(devices), MAX_CAMERAS)

        if count == 0:

            self.camera1_disconnected.emit()
            self.camera2_disconnected.emit()

            self.info_signal.emit(
                "No Basler cameras detected."
            )

            return False

        for i in range(count):

            cam = pylon.InstantCamera(
                tl_factory.CreateDevice(devices[i])
            )

            cam.Open()

            self.cams[i] = cam

            self.configure_camera(cam, f"Camera {i + 1}")

            # Mono8 cameras are used as-is (no conversion, 1/3 the
            # memory and CPU of BGR). Anything else is converted:
            # other mono formats to Mono8, colour formats to BGR.
            pixel_format = cam.PixelFormat.Value

            self.native_mono8[i] = (pixel_format == "Mono8")

            converter = pylon.ImageFormatConverter()

            converter.OutputPixelFormat = (
                pylon.PixelType_Mono8
                if pixel_format.startswith("Mono")
                else pylon.PixelType_BGR8packed
            )

            converter.OutputBitAlignment = \
                pylon.OutputBitAlignment_MsbAligned

            self.converters[i] = converter

            # OneByOne: never silently skip frames; the large buffer
            # pool absorbs short processing stalls
            cam.MaxNumBuffer = CAMERA_MAX_BUFFERS

            cam.StartGrabbing(
                pylon.GrabStrategy_OneByOne
            )

        self.active = tuple(
            self.cams[i] is not None
            for i in range(MAX_CAMERAS)
        )

        if self.active[0]:
            self.camera1_connected.emit()
        else:
            self.camera1_disconnected.emit()

        if self.active[1]:
            self.camera2_connected.emit()
        else:
            self.camera2_disconnected.emit()

        if count == 1:

            self.info_signal.emit(
                "Only one Basler camera detected - "
                "running with Camera 1 only."
            )

        self.status_signal.emit(
            "Cameras Initialized"
        )

        return True

    # --------------------------------------------------
    # Configure camera
    # --------------------------------------------------

    def configure_camera(self, cam, name):

        # Offsets first: the camera keeps its settings between runs and
        # Width.Max / Height.Max shrink while an offset is non-zero
        cam.OffsetX.Value = 0
        cam.OffsetY.Value = 0

        cam.Width.Value = cam.Width.Max

        cam.Height.Value = cam.Height.Max

        try:

            cam.AcquisitionFrameRateEnable.Value = True

            cam.AcquisitionFrameRate.Value = self.fps

        except Exception as e:

            self.status_signal.emit(
                f"{name}: could not set frame rate ({e})"
            )

        try:

            cam.ExposureAuto.Value = "Off"

        except Exception as e:

            self.status_signal.emit(
                f"{name}: could not disable auto exposure ({e})"
            )

        exposure_us = min(
            CAMERA_EXPOSURE_US,
            0.9 * 1e6 / self.fps
        )

        try:

            cam.ExposureTime.Value = exposure_us

        except Exception:

            try:

                cam.ExposureTimeAbs.Value = exposure_us

            except Exception as e:

                self.status_signal.emit(
                    f"{name}: could not set exposure ({e})"
                )

        try:

            actual = cam.ResultingFrameRate.Value

            if actual < 0.98 * self.fps:

                self.error_signal.emit(
                    f"{name}: requested {self.fps} fps but the "
                    f"camera can only deliver {actual:.1f} fps "
                    f"(check exposure / bandwidth)."
                )

        except Exception:

            pass

    # --------------------------------------------------
    # Control Functions
    # --------------------------------------------------

    def enable_preview(self):

        self.preview_enabled = True

    def disable_preview(self):

        self.preview_enabled = False

    def start_recording(
            self,
            recorder,
            start_voltage=None):
        """
        Starts a trial. The pre-trigger snapshot and the switch to live
        recording happen under one lock, so no frames are lost between
        them. Raises if the video files cannot be created.
        """

        with self.buffer_lock:

            recorder.start_trial(
                list(self.buffers[0]),
                list(self.buffers[1]),
                start_voltage=start_voltage,
                active_cameras=self.active
            )

            self.recorder = recorder

            self.recording_enabled = True

    def stop_recording(self):

        with self.buffer_lock:

            self.recording_enabled = False

            self.recorder = None

    # --------------------------------------------------
    # Frame grabbing
    # --------------------------------------------------

    def _grab(self, index):
        """
        Returns (frame, block_id) or None on timeout / bad grab.
        The frame is 2-D (mono) or 3-D (BGR) depending on the camera.
        The grab result is always released before returning.
        """

        grab = self.cams[index].RetrieveResult(
            50,
            pylon.TimeoutHandling_Return
        )

        if not grab:
            return None

        try:

            if not grab.GrabSucceeded():
                return None

            # GetArray() already returns an array that owns its memory
            # (not the driver buffer), so it stays valid after
            # Release(). An extra .copy() here cost ~1.7 ms per frame,
            # slowing the loop below the camera rate and building up a
            # growing backlog (= preview lag).
            if self.native_mono8[index]:

                frame = grab.GetArray()

            else:

                frame = self.converters[index].Convert(
                    grab
                ).GetArray()

            return frame, grab.GetBlockID()

        finally:

            grab.Release()

    def _discard_backlog(self, active):

        for i in active:

            cam = self.cams[i]

            while cam.NumReadyBuffers.Value > 0:

                grab = cam.RetrieveResult(
                    50,
                    pylon.TimeoutHandling_Return
                )

                if not grab:
                    break

                grab.Release()

    def _check_drops(self, name, last_id, block_id):

        if last_id is None or block_id <= 0:
            return 0

        missed = block_id - last_id - 1

        if missed > 0:

            self.status_signal.emit(
                f"{name} dropped {missed} frame(s)"
            )

            return missed

        return 0

    # --------------------------------------------------
    # Main Acquisition Loop
    # --------------------------------------------------

    def run(self):

        pending = [None, None]

        last_id = [None, None]

        last_preview = 0.0
        preview_period = 1.0 / PREVIEW_FPS

        try:

            if not self.initialize_cameras():
                return

            self.ready = True

            active = [
                i for i in range(MAX_CAMERAS)
                if self.active[i]
            ]

            # Frames queued during start-up would otherwise stay as a
            # permanent lag (the loop only matches the camera rate) and
            # leave the two cameras offset from each other
            self._discard_backlog(active)

            preview_signals = (
                self.frame1_ready,
                self.frame2_ready
            )

            disconnect_signals = (
                self.camera1_disconnected,
                self.camera2_disconnected
            )

            while not self._stop_event.is_set():

                failed = False

                for i in active:

                    if not self.cams[i].IsGrabbing():

                        disconnect_signals[i].emit()

                        self.error_signal.emit(
                            f"Camera {i + 1} stopped grabbing."
                        )

                        failed = True

                if failed:
                    break

                # A frame from one camera waits for its partner
                # instead of being discarded, so the pair stays aligned
                for i in active:

                    if pending[i] is None:
                        pending[i] = self._grab(i)

                if any(pending[i] is None for i in active):
                    continue

                frames = [None, None]

                for i in active:

                    frame, block_id = pending[i]

                    pending[i] = None

                    self.dropped[i] += self._check_drops(
                        f"Camera {i + 1}",
                        last_id[i],
                        block_id
                    )

                    last_id[i] = block_id

                    self.frame_counts[i] += 1

                    frames[i] = frame

                # Frames are never modified after this point, so the
                # buffer, recorder and preview can share them
                with self.buffer_lock:

                    for i in active:
                        self.buffers[i].append(frames[i])

                    if (
                        self.recording_enabled
                        and self.recorder is not None
                    ):

                        self.recorder.write_frames(
                            frames[0],
                            frames[1]
                        )

                now = time.monotonic()

                if (
                    self.preview_enabled
                    and now - last_preview >= preview_period
                ):

                    last_preview = now

                    for i in active:

                        preview_signals[i].emit(
                            self._preview_frame(frames[i])
                        )

        except Exception:

            self.error_signal.emit(
                traceback.format_exc()
            )

            self.camera1_disconnected.emit()
            self.camera2_disconnected.emit()

        finally:

            self.ready = False

            self._shutdown_cameras()

    @staticmethod
    def _preview_frame(frame):

        h, w = frame.shape[:2]

        return cv2.resize(
            frame,
            (w // 3, h // 3),
            interpolation=cv2.INTER_AREA
        )

    # --------------------------------------------------
    # Buffer Access
    # --------------------------------------------------

    def get_buffers(self):

        with self.buffer_lock:

            return (
                list(self.buffers[0]),
                list(self.buffers[1])
            )

    # --------------------------------------------------
    # Shutdown
    # --------------------------------------------------

    def _shutdown_cameras(self):
        """Runs in the acquisition thread, which owns the cameras."""

        for cam in self.cams:

            try:

                if cam is not None:

                    cam.StopGrabbing()
                    cam.Close()

            except Exception:
                pass

    def stop(self):

        self._stop_event.set()

        self.wait()
