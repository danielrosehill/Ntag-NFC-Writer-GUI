from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QTextEdit, QGroupBox, QLabel, QApplication, QMessageBox, QComboBox
)
from PyQt6.QtCore import QTimer
from smartcard.System import readers
from smartcard.Exceptions import NoCardException
import sys


class NFCApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NFC URL Writer (ACR-1252)")
        self.setMinimumWidth(600)
        self.connection = None
        self.card_detected = False
        self.remaining_writes = 1

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Reader selection group
        reader_group = QGroupBox("ACR-1252 Reader")
        reader_layout = QHBoxLayout(reader_group)
        self.reader_combo = QComboBox()
        self.refresh_button = QPushButton("Refresh Readers")
        reader_layout.addWidget(self.reader_combo)
        reader_layout.addWidget(self.refresh_button)
        layout.addWidget(reader_group)

        # URL input group
        url_group = QGroupBox("URL Configuration")
        url_layout = QVBoxLayout(url_group)
        self.url_input = QLineEdit()
        self.url_input.setText("https://")
        url_layout.addWidget(self.url_input)

        # Add write counter combo box
        write_counter_layout = QHBoxLayout()
        write_counter_layout.addWidget(QLabel("Number of writes:"))
        self.write_counter_combo = QComboBox()
        self.write_counter_combo.addItems([str(i) for i in range(1, 11)])
        write_counter_layout.addWidget(self.write_counter_combo)
        url_layout.addLayout(write_counter_layout)

        # Add remaining writes label
        self.remaining_writes_label = QLabel("Remaining writes: 1")
        url_layout.addWidget(self.remaining_writes_label)
        
        layout.addWidget(url_group)

        # Buttons
        button_layout = QHBoxLayout()
        self.write_button = QPushButton("Write URL and Lock")
        self.reset_button = QPushButton("Reset")
        button_layout.addWidget(self.write_button)
        button_layout.addWidget(self.reset_button)
        layout.addLayout(button_layout)

        # Card status light
        self.status_light = QLabel()
        self.status_light.setFixedSize(20, 20)
        self.status_light.setStyleSheet("background-color: red; border-radius: 10px;")
        status_layout = QHBoxLayout()
        status_layout.addWidget(QLabel("Card Status:"))
        status_layout.addWidget(self.status_light)
        layout.addLayout(status_layout)

        # Status log
        self.status_log = QTextEdit()
        self.status_log.setReadOnly(True)
        layout.addWidget(self.status_log)

        # Timer for card detection
        self.card_timer = QTimer()
        self.card_timer.timeout.connect(self.check_for_card)
        self.card_timer.start(1000)  # Check for card every second

        # Connect buttons
        self.write_button.clicked.connect(self.write_and_lock_url)
        self.reset_button.clicked.connect(self.reset)
        self.refresh_button.clicked.connect(self.refresh_readers)
        self.write_counter_combo.currentTextChanged.connect(self.on_write_counter_changed)

        # Initialize reader list
        self.refresh_readers()

    def log(self, message):
        self.status_log.append(message)
        self.status_log.verticalScrollBar().setValue(
            self.status_log.verticalScrollBar().maximum()
        )

    def on_write_counter_changed(self, value):
        self.remaining_writes = int(value)
        self.remaining_writes_label.setText(f"Remaining writes: {self.remaining_writes}")

    def refresh_readers(self):
        try:
            reader_list = readers()
            self.reader_combo.clear()
            for reader in reader_list:
                if "ACR1252" in str(reader):  # Filter for ACR-1252 readers
                    self.reader_combo.addItem(str(reader))
            if self.reader_combo.count() > 0:
                self.log("ACR-1252 readers refreshed successfully")
            else:
                self.log("No ACR-1252 readers found")
        except Exception as e:
            self.log(f"Error refreshing readers: {str(e)}")

    def check_for_card(self):
        try:
            if self.connect_reader():
                if not self.card_detected:
                    self.card_detected = True
                    self.status_light.setStyleSheet("background-color: green; border-radius: 10px;")
                    self.log("Card detected and ready")
            else:
                if self.card_detected:
                    self.card_detected = False
                    self.status_light.setStyleSheet("background-color: red; border-radius: 10px;")
                    self.log("Card removed")
        except Exception as e:
            self.log(f"Error checking for card: {str(e)}")

    def connect_reader(self):
        try:
            if not self.reader_combo.currentText():
                return False
            r = readers()
            self.reader = [reader for reader in r if str(reader) == self.reader_combo.currentText()][0]
            self.connection = self.reader.createConnection()
            self.connection.connect()
            return True
        except Exception as e:
            return False

    def _write_data(self, page, data):
        while len(data) < 4:
            data.append(0x00)
        apdu = [0xFF, 0xD6, 0x00, page] + [len(data)] + data
        response, sw1, sw2 = self.connection.transmit(apdu)
        if not (sw1 == 0x90 and sw2 == 0x00):
            raise Exception(f"Write failed at page {page}: {hex(sw1)} {hex(sw2)}")

    def create_ndef_url(self, url):
        url = url.lower().replace('https://', '').replace('http://', '')
        url_bytes = url.encode()
        url_length = len(url_bytes)
        total_length = url_length + 5

        if total_length > 254:
            tlv = [
                0x03,  # NDEF message TLV tag
                0xFF,  # Extended length marker
                (total_length >> 8) & 0xFF,
                total_length & 0xFF,
                0xD1,  # NDEF header
                0x01,  # Type length
                url_length + 1,  # Payload length
                0x55,  # 'U' Type
                0x04   # https:// prefix
            ]
        else:
            tlv = [
                0x03,  # NDEF message TLV tag
                total_length,
                0xD1,  # NDEF header
                0x01,  # Type length
                url_length + 1,
                0x55,  # 'U' Type
                0x04   # https:// prefix
            ]

        ndef_message = tlv + list(url_bytes)
        ndef_message += [0xFE]  # TLV terminator
        return ndef_message

    def lock_tag(self):
        try:
            static_lock_bytes = [0xFF, 0xFF, 0xFF, 0xFF]
            self._write_data(2, static_lock_bytes)

            dynamic_lock_bytes = [0xFF, 0xFF, 0xFF, 0xFF]
            self._write_data(40, dynamic_lock_bytes)

            self.log("Tag locked successfully")
        except Exception as e:
            self.log(f"Warning: Could not lock tag - {str(e)}")

    def write_and_lock_url(self):
        if not self.card_detected:
            QMessageBox.warning(self, "No Card", "Please place an NFC tag on the reader before writing.")
            return

        try:
            url = self.url_input.text()
            # Check if URL is just http:// or https://
            if url.lower() in ['http://', 'https://']:
                QMessageBox.warning(self, "Invalid URL", "Please enter a complete URL after http:// or https://")
                return
                
            if not url.startswith(('http://', 'https://')):
                QMessageBox.warning(self, "Invalid URL", "URL must start with http:// or https://")
                return

            if not self.connect_reader():
                return

            if self.remaining_writes <= 0:
                self.reset()
                QMessageBox.warning(self, "Write Limit Reached", "Maximum number of writes reached. Settings have been reset.")
                return

            self.log("Writing URL...")

            ndef_data = self.create_ndef_url(url)
            self.log("NDEF data: " + " ".join([hex(x) for x in ndef_data]))

            cc_data = [0xE1, 0x10, 0x6D, 0x00]
            self._write_data(3, cc_data)

            page = 4
            chunk_size = 4
            for i in range(0, len(ndef_data), chunk_size):
                chunk = ndef_data[i:i + chunk_size]
                self._write_data(page, chunk)
                page += 1

                if page > 35:
                    raise Exception("URL too long for tag capacity")

            self.lock_tag()

            # Update remaining writes counter
            self.remaining_writes -= 1
            self.remaining_writes_label.setText(f"Remaining writes: {self.remaining_writes}")

            if self.remaining_writes > 0:
                self.status_light.setStyleSheet("background-color: orange; border-radius: 10px;")
                self.log("Tag locked. You can now remove the card.")
                QMessageBox.information(self, "Success", f"URL written and tag locked successfully! {self.remaining_writes} writes remaining.")
            else:
                self.reset()
                QMessageBox.information(self, "Success", "URL written and tag locked successfully! Maximum writes reached, settings reset.")

        except Exception as e:
            self.log(f"Error: {str(e)}")
            QMessageBox.critical(self, "Error", str(e))
        finally:
            if self.connection:
                self.connection.disconnect()

    def reset(self):
        self.url_input.setText("https://")
        self.status_log.clear()
        self.card_detected = False
        self.status_light.setStyleSheet("background-color: red; border-radius: 10px;")
        self.remaining_writes = int(self.write_counter_combo.currentText())
        self.remaining_writes_label.setText(f"Remaining writes: {self.remaining_writes}")
        self.log("Reset complete")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = NFCApp()
    window.show()
    sys.exit(app.exec())