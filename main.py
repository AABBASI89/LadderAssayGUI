# main.py

import sys

from PyQt5.QtWidgets import (
    QApplication,
    QMessageBox
)

from gui import MainWindow


def main():

    app = QApplication(sys.argv)

    app.setApplicationName(
        "Ladder Assay Recorder"
    )

    app.setOrganizationName(
        "Behavior Lab"
    )

    try:

        window = MainWindow()

        window.show()

        sys.exit(
            app.exec_()
        )

    except Exception as e:

        QMessageBox.critical(
            None,
            "Startup Error",
            str(e)
        )

        sys.exit(1)


if __name__ == "__main__":

    main()