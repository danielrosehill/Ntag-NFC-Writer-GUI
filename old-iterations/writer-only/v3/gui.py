from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLineEdit, QComboBox, QPushButton, QTextEdit, QGroupBox, QStyle, QMessageBox, 
    QApplication, QLabel, QRadioButton, QButtonGroup)
from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QPixmap, QColor
from PyQt6.QtMultimedia import QSoundEffect
from smartcard.System import readers
from smartcard.Exceptions import NoCardException
import sys
import subprocess
import webbrowser

class NFCWriterGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NFC URL Reader/Writer")
        self.setMinimumWidth(600)
        self.connection = None
        self.tag_present = False
        self.last_read_url = None  # To prevent repeated reads of same tag
        self.mode = "read"  # Default mode
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Mode Selection
        mode_group = QGroupBox("Mode")
        mode_layout = QHBoxLayout(mode_group)
        self.read_mode_radio = QRadioButton("Read Mode")
        self.write_mode_radio = QRadioButton("Write Mode")
        self.read_mode_radio.setChecked(True)  # Default to read mode
        mode_layout.addWidget(self.read_mode_radio)
        mode_layout.addWidget(self.write_mode_radio)
        layout.addWidget(mode_group)

        # Create button group for radio buttons
        self.mode_group = QButtonGroup()
        self.mode_group.addButton(self.read_mode_radio)
        self.mode_group.addButton(self.write_mode_radio)
        self.mode_group.buttonClicked.connect(self.mode_changed)
        
        # Presence Indicator
        indicator_layout = QHBoxLayout()
        self.presence_indicator = QLabel()
        self.presence_indicator.setFixedSize(20, 20)
        self.presence_indicator.setStyleSheet("background-color: gray; border-radius: 10px;")
        self.presence_label = QLabel("Tag Status: Not Present")
        indicator_layout.addWidget(self.presence_indicator)
        indicator_layout.addWidget(self.presence_label)
        indicator_layout.addStretch()
        layout.addLayout(indicator_layout)
        
        reader_group = QGroupBox("NFC Reader")
        reader_layout = QVBoxLayout(reader_group)
        self.reader_combo = QComboBox()
        reader_layout.addWidget(self.reader_combo)
        layout.addWidget(reader_group)

        # URL Configuration (only visible in write mode)
        self.url_group = QGroupBox("URL Configuration")
        url_layout = QVBoxLayout(self.url_group)
        self.url_input = QLineEdit()
        self.url_input.setText("https://")
        url_layout.addWidget(self.url_input)
        layout.addWidget(self.url_group)

        button_group = QGroupBox("Actions")
        button_layout = QHBoxLayout(button_group)
        self.refresh_button = QPushButton("Refresh Readers")
        self.write_button = QPushButton("Write URL and Lock")
        button_layout.addWidget(self.refresh_button)
        button_layout.addWidget(self.write_button)
        layout.addWidget(button_group)

        self.status_log = QTextEdit()
        self.status_log.setReadOnly(True)
        layout.addWidget(self.status_log)

        self.refresh_button.clicked.connect(self.refresh_readers)
        self.write_button.clicked.connect(self.write_and_lock_url)
        
        # Timer for continuous scanning
        self.scan_timer = QTimer()
        self.scan_timer.timeout.connect(self.check_and_read_tag)
        self.scan_timer.start(1000)  # Check every second
        
        self.refresh_readers()
        self.update_ui_for_mode()

    def mode_changed(self, button):
        self.mode = "read" if button == self.read_mode_radio else "write"
        self.update_ui_for_mode()
        self.last_read_url = None  # Reset last read URL when mode changes
        self.log(f"Switched to {self.mode} mode")

    def update_ui_for_mode(self):
        # Show/hide relevant UI elements based on mode
        self.url_group.setVisible(self.mode == "write")
        self.write_button.setVisible(self.mode == "write")

    def log(self, message):
        self.status_log.append(message)
        self.status_log.verticalScrollBar().setValue(
            self.status_log.verticalScrollBar().maximum()
        )

    def check_and_read_tag(self):
        """Continuous scanning function"""
        if self.mode != "read":
            return

        try:
            if self.reader_combo.currentText() == "":
                return

            # Try to connect and read
            self.connect_reader(self.reader_combo.currentText())
            if self.connection:
                self.presence_indicator.setStyleSheet("background-color: green; border-radius: 10px;")
                self.presence_label.setText("Tag Status: Present")
                
                # Only read if we haven't read this tag before
                data = []
                for page in range(0, 16):
                    response = self._read_data(page, 4)
                    data.extend(response)
                
                url = self.parse_ndef_message(data)
                if url and url != self.last_read_url:
                    self.last_read_url = url
                    self.log(f"Found URL: {url}")
                    try:
                        subprocess.Popen(['google-chrome', url])
                    except Exception as e:
                        self.log(f"Failed to open Chrome: {str(e)}")
                        webbrowser.open(url)
                
                self.connection.disconnect()
            else:
                self.presence_indicator.setStyleSheet("background-color: gray; border-radius: 10px;")
                self.presence_label.setText("Tag Status: Not Present")
                self.last_read_url = None

        except Exception as e:
            self.presence_indicator.setStyleSheet("background-color: gray; border-radius: 10px;")
            self.presence_label.setText("Tag Status: Not Present")
            self.last_read_url = None
            if self.connection:
                try:
                    self.connection.disconnect()
                except:
                    pass

    # [Previous methods remain the same: refresh_readers, connect_reader, _write_data, _read_data, etc.]
    # [Include all the previous methods here]

    def parse_ndef_message(self, data):
        try:
            i = 4  # Skip CC bytes
            while i < len(data):
                if data[i] == 0x03:  # NDEF Message TLV tag
                    ndef_length = data[i + 1]
                    ndef_data = data[i + 2:i + 2 + ndef_length]
                    if ndef_data[0] == 0xD1 and ndef_data[4] == 0x55:  # URI record
                        url_prefix = "https://"  # Default prefix
                        url_data = bytes(ndef_data[7:]).decode('utf-8')
                        return url_prefix + url_data
                i += 1
            return None
        except Exception as e:
            self.log(f"Error parsing NDEF message: {str(e)}")
            return None

    # [Include all other methods from the previous script...]

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = NFCWriterGUI()
    window.show()
    sys.exit(app.exec())