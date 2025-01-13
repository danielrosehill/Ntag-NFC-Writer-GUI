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

    def refresh_readers(self):
        try:
            reader_list = readers()
            self.reader_combo.clear()
            for reader in reader_list:
                self.reader_combo.addItem(str(reader))
            if reader_list:
                self.log("Readers refreshed successfully")
            else:
                self.log("No readers found")
        except Exception as e:
            self.log(f"Error refreshing readers: {str(e)}")

    def connect_reader(self, selected_reader):
        if not selected_reader:
            raise Exception("No reader selected")
        
        r = readers()
        self.reader = [reader for reader in r if str(reader) == selected_reader][0]
        self.connection = self.reader.createConnection()
        self.connection.connect()

    def _write_data(self, page, data):
        while len(data) < 4:
            data.append(0x00)
        apdu = [0xFF, 0xD6, 0x00, page] + [len(data)] + data
        response, sw1, sw2 = self.connection.transmit(apdu)
        if not (sw1 == 0x90 and sw2 == 0x00):
            raise Exception(f"Write failed at page {page}: {hex(sw1)} {hex(sw2)}")

    def _read_data(self, page, length):
        apdu = [0xFF, 0xB0, 0x00, page, length]
        response, sw1, sw2 = self.connection.transmit(apdu)
        if not (sw1 == 0x90 and sw2 == 0x00):
            raise Exception(f"Read failed at page {page}: {hex(sw1)} {hex(sw2)}")
        return response

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

    def create_ndef_url(self, url):
        url = url.lower().replace('https://', '').replace('http://', '')
        url_bytes = url.encode()
        url_length = len(url_bytes)
        
        NDEF_START = 0x03
        ndef_length = url_length + 5
        
        tlv = [
            NDEF_START,
            ndef_length,
            0xD1,
            0x01,
            url_length + 1,
            0x55,
            0x04
        ]
        
        ndef_message = tlv + list(url_bytes)
        ndef_message += [0xFE]
        
        return ndef_message

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

    def lock_tag(self):
        try:
            for page in range(0, 16):
                lock_apdu = [0xFF, 0x82, 0x00, page, 0x04, 0xFF, 0xFF, 0xFF, 0xFF]
                response, sw1, sw2 = self.connection.transmit(lock_apdu)
                if not (sw1 == 0x90 and sw2 == 0x00):
                    raise Exception(f"Failed to lock page {page}: {hex(sw1)} {hex(sw2)}")
            self.log("Tag locked successfully")
        except Exception as e:
            raise Exception(f"Error locking tag: {str(e)}")

    def write_and_lock_url(self):
        try:
            url = self.url_input.text()
            if not url.startswith(('http://', 'https://')):
                QMessageBox.warning(self, "Invalid URL", "URL must start with http:// or https://")
                return
            
            if self.reader_combo.currentText() == "":
                QMessageBox.warning(self, "No Reader", "No NFC reader selected")
                return
            
            self.connect_reader(self.reader_combo.currentText())
            self.log(f"Connected to: {self.reader}")
            self.log(f"Writing URL: {url}")
            
            ndef_data = self.create_ndef_url(url)
            self.log("NDEF data: " + " ".join([hex(x) for x in ndef_data]))
            
            cc_data = [0xE1, 0x10, 0x6D, 0x00]
            self._write_data(3, cc_data)
            
            page = 4
            chunk_size = 4
            for i in range(0, len(ndef_data), chunk_size):
                chunk = ndef_data[i:i+chunk_size]
                self._write_data(page, chunk)
                page += 1
            
            self.lock_tag()
            
            self.url_input.setText("https://")
            QMessageBox.information(self, "Success", "URL written and tag locked successfully!")
            
            self.refresh_readers()
            
        except Exception as e:
            self.log(f"Error: {str(e)}")
            QMessageBox.critical(self, "Error", str(e))
        finally:
            if self.connection:
                self.connection.disconnect()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = NFCWriterGUI()
    window.show()
    sys.exit(app.exec())        