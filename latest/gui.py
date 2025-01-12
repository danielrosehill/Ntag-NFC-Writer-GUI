from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLineEdit, QComboBox, QPushButton, QTextEdit, QGroupBox, QStyle, QMessageBox, QApplication, QLabel)
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor
from smartcard.System import readers
from smartcard.Exceptions import NoCardException
import sys

class NFCWriterGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NFC URL Writer")
        self.setMinimumWidth(600)
        self.connection = None
        self.tag_present = False
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Presence Indicator
        self.presence_indicator = QLabel()
        self.presence_indicator.setFixedSize(20, 20)
        self.presence_indicator.setStyleSheet("background-color: gray; border-radius: 10px;")
        layout.addWidget(self.presence_indicator)
        
        reader_group = QGroupBox("NFC Reader")
        reader_layout = QVBoxLayout(reader_group)
        self.reader_combo = QComboBox()
        reader_layout.addWidget(self.reader_combo)
        layout.addWidget(reader_group)

        url_group = QGroupBox("URL Configuration")
        url_layout = QVBoxLayout(url_group)
        self.url_input = QLineEdit()
        self.url_input.setText("https://")
        url_layout.addWidget(self.url_input)
        layout.addWidget(url_group)

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
        
        # Timer for tag presence detection
        self.tag_timer = QTimer()
        self.tag_timer.timeout.connect(self.check_tag_presence)
        self.tag_timer.start(1000)  # Check every second
        
        self.refresh_readers()

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

    def create_ndef_url(self, url):
        url = url.lower().replace('https://', ''). replace('http://', '')
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

    def lock_tag(self):
        try:
            # Set static lock bytes (pages 2-3)
            static_lock_bytes = [0xFF, 0xFF, 0xFF, 0xFF]  # Adjust values as needed
            self._write_data(2, static_lock_bytes)
            
            # Set dynamic lock bytes (page 40)
            dynamic_lock_bytes = [0xFF, 0xFF, 0xFF, 0xFF]  # Adjust values as needed
            self._write_data(40, dynamic_lock_bytes)
            
            self.log("Tag locked successfully")
        except Exception as e:
            self.log(f"Warning: Could not lock tag - {str(e)}")

    def check_tag_presence(self):
        try:
            if self.connection:
                # Attempt to reconnect to check tag presence
                self.connection.reconnect()
                self.tag_present = True
                self.presence_indicator.setStyleSheet("background-color: green; border-radius: 10px;")
            else:
                self.tag_present = False
                self.presence_indicator.setStyleSheet("background-color: gray; border-radius: 10px;")
        except Exception:
            self.tag_present = False
            self.presence_indicator.setStyleSheet("background-color: gray; border-radius: 10px;")

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
            
            # Attempt to lock the tag
            self.lock_tag()
            
            self.url_input.setText("https://")
            QMessageBox.information(self, "Success", "URL written successfully!")
            
            # Automatically refresh for the next tag
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