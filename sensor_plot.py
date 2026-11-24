# sensor_plot.py

import time
from collections import deque

import pyqtgraph as pg

from PyQt5.QtCore import (
    Qt,
    QTimer
)

from PyQt5.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QFrame
)

from config import (
    PLOT_HISTORY,
    PLOT_SECONDS,
    PLOT_REFRESH_MS,
    START_THRESHOLD,
    STOP_THRESHOLD,
    PLOT_Y_MAX,
    is_broken
)


class SensorPlotWindow(QWidget):

    def __init__(
            self,
            start_threshold=START_THRESHOLD,
            stop_threshold=STOP_THRESHOLD):

        super().__init__()

        # Live thresholds (the main window can change them)
        self.start_threshold = start_threshold
        self.stop_threshold = stop_threshold

        self.setWindowTitle(
            "Ladder Assay Sensors"
        )

        self.resize(1000, 700)

        # -----------------------------
        # Sensor Histories
        # -----------------------------

        # Only real samples are stored (no pre-filled 5 V), each with
        # the time it arrived
        self.time_history = deque(
            maxlen=PLOT_HISTORY
        )

        self.sensor1_history = deque(
            maxlen=PLOT_HISTORY
        )

        self.sensor2_history = deque(
            maxlen=PLOT_HISTORY
        )

        self.sensor1_current = None
        self.sensor2_current = None

        self.setup_ui()

        # -----------------------------
        # Refresh Display
        # -----------------------------

        self.timer = QTimer()

        self.timer.timeout.connect(
            self.update_display
        )

        self.timer.start(
            PLOT_REFRESH_MS
        )

    # ==================================================
    # UI
    # ==================================================

    def setup_ui(self):

        layout = QVBoxLayout(self)

        # ==================================================
        # Sensor 1 Status
        # ==================================================

        row1 = QHBoxLayout()

        self.sensor1_label = QLabel(
            "Start Beam A0"
        )

        self.sensor1_label.setStyleSheet(
            """
            font-size:16pt;
            font-weight:bold;
            """
        )

        self.sensor1_indicator = QLabel()

        self.sensor1_indicator.setFixedSize(
            30,
            30
        )

        row1.addWidget(
            self.sensor1_label
        )

        row1.addStretch()

        row1.addWidget(
            self.sensor1_indicator
        )

        # ==================================================
        # Sensor 2 Status
        # ==================================================

        row2 = QHBoxLayout()

        self.sensor2_label = QLabel(
            "Stop Beam A1"
        )

        self.sensor2_label.setStyleSheet(
            """
            font-size:16pt;
            font-weight:bold;
            """
        )

        self.sensor2_indicator = QLabel()

        self.sensor2_indicator.setFixedSize(
            30,
            30
        )

        row2.addWidget(
            self.sensor2_label
        )

        row2.addStretch()

        row2.addWidget(
            self.sensor2_indicator
        )

        # ==================================================
        # Plot 1
        # ==================================================

        self.plot1 = pg.PlotWidget()
        
        self.plot1.setLabel(
            'left',
            'Voltage (V)'
        )

        self.plot1.setLabel(
            'bottom',
            'Time (s)'
        )

        self.plot1.setXRange(
            -PLOT_SECONDS,
            0
        )

        self.plot1.setBackground('w')

        self.plot1.setTitle(
            "Start Beam Voltage (A0)"
        )

        self.plot1.setYRange(
            0,
            PLOT_Y_MAX
        )

        self.plot1.showGrid(
            x=True,
            y=True
        )

        self.curve1 = self.plot1.plot(
            pen=pg.mkPen(
                color='red',
                width=2
            )
        )
        
        self.threshold_line1 = self.plot1.addLine(
            y=self.start_threshold,
            pen=pg.mkPen(
                color='r',
                style=Qt.DashLine
            )
        )        

        # ==================================================
        # Plot 2
        # ==================================================

        self.plot2 = pg.PlotWidget()
        
        self.plot2.setLabel(
            'left',
            'Voltage (V)'
        )

        self.plot2.setLabel(
            'bottom',
            'Time (s)'
        )

        self.plot2.setXRange(
            -PLOT_SECONDS,
            0
        )

        self.plot2.setBackground('w')

        self.plot2.setTitle(
            "Stop Beam Voltage (A1)"
        )

        self.plot2.setYRange(
            0,
            PLOT_Y_MAX
        )

        self.plot2.showGrid(
            x=True,
            y=True
        )

        self.curve2 = self.plot2.plot(
            pen=pg.mkPen(
                color='green',
                width=2
            )
        )
        
        self.threshold_line2 = self.plot2.addLine(
            y=self.stop_threshold,
            pen=pg.mkPen(
                color='r',
                style=Qt.DashLine
            )
        )        

        # ==================================================
        # Layout
        # ==================================================

        separator1 = QFrame()
        separator1.setFrameShape(
            QFrame.HLine
        )

        separator2 = QFrame()
        separator2.setFrameShape(
            QFrame.HLine
        )

        layout.addLayout(row1)
        layout.addWidget(separator1)
        layout.addWidget(self.plot1)

        layout.addSpacing(15)

        layout.addLayout(row2)
        layout.addWidget(separator2)
        layout.addWidget(self.plot2)

        layout.setSpacing(10)

    # ==================================================
    # Threshold
    # ==================================================

    def set_threshold(self, beam, value):

        if beam == 1:

            self.start_threshold = value

            self.threshold_line1.setValue(value)

        else:

            self.stop_threshold = value

            self.threshold_line2.setValue(value)

    # ==================================================
    # Sensor Updates
    # ==================================================

    def update_sensor_values(
            self,
            sensor1,
            sensor2
    ):

        self.sensor1_current = sensor1
        self.sensor2_current = sensor2

        self.time_history.append(
            time.monotonic()
        )

        self.sensor1_history.append(
            sensor1
        )

        self.sensor2_history.append(
            sensor2
        )

    # ==================================================
    # Display Refresh
    # ==================================================

    def update_display(self):

        if self.sensor1_current is None:

            self.sensor1_label.setText(
                "Start Beam A0 : waiting for data..."
            )

            self.sensor2_label.setText(
                "Stop Beam A1 : waiting for data..."
            )

            return

        beam1_state = (
            "BROKEN"
            if is_broken(self.sensor1_current, self.start_threshold)
            else "CLEAR"
        )

        beam2_state = (
            "BROKEN"
            if is_broken(self.sensor2_current, self.stop_threshold)
            else "CLEAR"
        )

        self.sensor1_label.setText(
            f"Start Beam A0 : "
            f"{self.sensor1_current:.2f} V "
            f"({beam1_state})"
        )

        self.sensor2_label.setText(
            f"Stop Beam A1 : "
            f"{self.sensor2_current:.2f} V "
            f"({beam2_state})"
        )

        # x axis: seconds before now, so the trace scrolls in real time
        now = time.monotonic()

        x = [t - now for t in self.time_history]

        self.curve1.setData(
            x,
            list(self.sensor1_history)
        )

        self.curve2.setData(
            x,
            list(self.sensor2_history)
        )

        self.update_indicator(
            self.sensor1_indicator,
            self.sensor1_current,
            self.start_threshold
        )

        self.update_indicator(
            self.sensor2_indicator,
            self.sensor2_current,
            self.stop_threshold
        )

    # ==================================================
    # LED Indicator
    # ==================================================

    def update_indicator(
            self,
            widget,
            value,
            threshold
    ):

        if is_broken(value, threshold):

            color = "#CC0000"

        else:

            color = "#00AA00"

        widget.setStyleSheet(
            f"""
            background-color:{color};
            border-radius:15px;
            border:2px solid black;
            """
        )