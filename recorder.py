# recorder.py

import queue
import threading
from datetime import datetime

import cv2

from config import (
    CAMERA_FPS,
    CAMERA_WIDTH,
    CAMERA_HEIGHT,
    VIDEO_CODEC
)


class _Trial:
    """State for one trial (kept separate so a new trial can start
    while the previous one is still being flushed to disk)."""

    def __init__(self, number, folder, start_time, start_voltage):

        self.number = number
        self.folder = folder

        self.start_time = start_time
        self.stop_time = None

        self.start_voltage = start_voltage
        self.stop_voltage = None

        self.writers = [None, None]
        self.queues = [queue.Queue(), queue.Queue()]
        self.threads = []

        self.frames = [0, 0]
        self.pretrigger_frames = 0

        self.active = (True, True)

        self.errors = []


class Recorder:
    """
    Handles trial recording.

    Responsibilities:

    - Create trial folder
    - Create AVI writers (one writer thread per camera, so encoding
      never blocks the camera or GUI threads)
    - Write pre-trigger frames
    - Write live frames
    - Generate trial_info.csv
    """

    def __init__(self, logger):

        self.logger = logger

        self.recording = False

        self.trial = None

        self._lock = threading.Lock()

        self._finalizers = []

    # ======================================================
    # Trial Start
    # ======================================================

    def start_trial(
            self,
            buffer_cam1,
            buffer_cam2,
            start_voltage=None,
            active_cameras=(True, True)
    ):

        with self._lock:

            if self.recording:
                return

            trial_folder = self.logger.create_trial_folder()

            trial = _Trial(
                self.logger.get_trial_number(),
                trial_folder,
                datetime.now(),
                start_voltage
            )

            # fourcc 0 selects uncompressed video in OpenCV
            fourcc = (
                0
                if VIDEO_CODEC == "RAW"
                else cv2.VideoWriter_fourcc(*VIDEO_CODEC)
            )

            buffers = (buffer_cam1, buffer_cam2)

            trial.active = tuple(active_cameras)

            for i in range(2):

                # A camera that is not connected gets no video file
                if not trial.active[i]:
                    continue

                # Use the real frame size; cv2 silently discards
                # frames that do not match the writer size
                if buffers[i]:
                    sample = buffers[i][0]
                    h, w = sample.shape[:2]
                    is_color = sample.ndim == 3
                else:
                    w, h = CAMERA_WIDTH, CAMERA_HEIGHT
                    is_color = False

                # Mono frames need isColor=False or cv2 drops them
                trial.writers[i] = cv2.VideoWriter(
                    str(trial_folder / f"cam{i + 1}.avi"),
                    fourcc,
                    CAMERA_FPS,
                    (w, h),
                    is_color
                )

            for i in range(2):

                if trial.active[i] and not trial.writers[i].isOpened():

                    for writer in trial.writers:

                        if writer is not None:
                            writer.release()

                    raise RuntimeError(
                        f"Failed to create cam{i + 1}.avi"
                    )

            # Pre-trigger frames go in first, live frames follow
            for i in range(2):

                if not trial.active[i]:
                    continue

                for frame in buffers[i]:
                    trial.queues[i].put(frame)

            first = trial.active.index(True)

            trial.pretrigger_frames = len(buffers[first])

            for i in range(2):

                if not trial.active[i]:
                    continue

                thread = threading.Thread(
                    target=self._writer_loop,
                    args=(trial, i),
                    name=f"VideoWriter{i + 1}"
                )

                thread.start()

                trial.threads.append(thread)

            self.trial = trial

            self.recording = True

        self.logger.log_event(
            "TrialStart",
            sensor1=start_voltage
        )

        self.logger.log_event(
            "PretriggerWritten",
            details=f"{trial.pretrigger_frames} frames queued"
        )

    # ======================================================
    # Writer threads
    # ======================================================

    def _writer_loop(self, trial, index):

        q = trial.queues[index]

        writer = trial.writers[index]

        while True:

            frame = q.get()

            if frame is None:
                break

            try:

                writer.write(frame)

                trial.frames[index] += 1

            except Exception as e:

                trial.errors.append(
                    f"cam{index + 1} write error: {e}"
                )

        writer.release()

    # ======================================================
    # Live Frames
    # ======================================================

    def write_frames(
            self,
            frame1,
            frame2
    ):

        with self._lock:

            if not self.recording:
                return

            # None = camera not connected
            if frame1 is not None:
                self.trial.queues[0].put(frame1)

            if frame2 is not None:
                self.trial.queues[1].put(frame2)

    # ======================================================
    # Trial Stop
    # ======================================================

    def stop_trial(
            self,
            stop_voltage=None
    ):

        with self._lock:

            if not self.recording:
                return

            self.recording = False

            trial = self.trial

            self.trial = None

            trial.stop_time = datetime.now()

            trial.stop_voltage = stop_voltage

            # Sentinel: writer threads drain their queue, then exit
            for i in range(2):

                if trial.active[i]:
                    trial.queues[i].put(None)

        self.logger.log_event(
            "TrialStop",
            sensor2=stop_voltage
        )

        # Flushing the backlog can take a while, so do it off the
        # caller's (GUI) thread
        finalizer = threading.Thread(
            target=self._finalize,
            args=(trial,),
            name=f"Finalize{trial.number}"
        )

        finalizer.start()

        self._finalizers = [
            t for t in self._finalizers if t.is_alive()
        ]

        self._finalizers.append(finalizer)

    def _finalize(self, trial):

        for thread in trial.threads:
            thread.join()

        for i in (1, 2):

            if not trial.active[i - 1]:
                continue

            if not (trial.folder / f"cam{i}.avi").exists():

                self.logger.log_event(
                    "ERROR",
                    details=f"cam{i}.avi missing"
                )

        for error in trial.errors:

            self.logger.log_event(
                "ERROR",
                details=error
            )

        duration = (
            trial.stop_time - trial.start_time
        ).total_seconds()

        self.logger.save_trial_info(
            trial_folder=trial.folder,
            start_time=trial.start_time.isoformat(),
            stop_time=trial.stop_time.isoformat(),
            frames_cam1=trial.frames[0],
            frames_cam2=trial.frames[1],
            pretrigger_frames=trial.pretrigger_frames,
            duration_seconds=duration,
            start_trigger_voltage=trial.start_voltage,
            stop_trigger_voltage=trial.stop_voltage,
            trial_number=trial.number
        )

    def wait_finalize(self):
        """Blocks until all video files are fully written."""

        for thread in list(self._finalizers):
            thread.join()

    # ======================================================
    # Emergency Stop
    # ======================================================

    def abort(self):

        if not self.recording:
            return

        self.logger.log_event(
            "ManualStop"
        )

        self.stop_trial()

    # ======================================================
    # Status
    # ======================================================

    def is_recording(self):

        return self.recording

    def current_trial(self):

        return self.logger.get_trial_number()

    def frame_count_cam1(self):

        trial = self.trial

        return trial.frames[0] if trial else 0

    def frame_count_cam2(self):

        trial = self.trial

        return trial.frames[1] if trial else 0
