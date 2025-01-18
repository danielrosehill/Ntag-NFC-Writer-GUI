from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QTextEdit, QGroupBox, QLabel, QApplication, QMessageBox, QComboBox,
    QTabWidget, QTextBrowser
)
from PyQt6.QtCore import QTimer
from smartcard.System import readers
from smartcard.Exceptions import NoCardException
import sys
import webbrowser
import re


class NFCApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NFC URL Writer/Reader (ACR-1252)")
        self.setMinimumWidth(600)
        self.connection = None
        self.card_detected = False

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Write Tab
        self.write_tab = QWidget()
        self.write_layout = QVBoxLayout(self.write_tab)
        self.setup_write_tab()
        self.tabs.addTab(self.write_tab, "Write URL")

        # Read Tab
        self.read_tab = QWidget()
        self.read_layout = QVBoxLayout(self.read_tab)
        self.setup_read_tab()
        self.tabs.addTab(self.read_tab, "Read URL")

        # Timer for card detection (moved to base class so that both read and write can use it)
        self.card_timer = QTimer()
        self.card_timer.timeout.connect(self.check_for_card)
        self.card_timer.start(1000)  # Check for card every second

    def setup_write_tab(self):
        # Reader selection group
        reader_group = QGroupBox("ACR-1252 Reader")
        reader_layout = QHBoxLayout(reader_group)
        self.reader_combo = QComboBox()
        self.refresh_button = QPushButton("Refresh Readers")
        reader_layout.addWidget(self.reader_combo)
        reader_layout.addWidget(self.refresh_button)
        self.write_layout.addWidget(reader_group)

        # URL input group
        url_group = QGroupBox("URL Configuration")
        url_layout = QVBoxLayout(url_group)
        self.url_input = QLineEdit()
        self.url_input.setText("https://")
        url_layout.addWidget(self.url_input)
        self.write_layout.addWidget(url_group)

        # Buttons
        button_layout = QHBoxLayout()
        self.write_button = QPushButton("Write URL and Lock")
        self.reset_button = QPushButton("Reset")
        button_layout.addWidget(self.write_button)
        button_layout.addWidget(self.reset_button)
        self.write_layout.addLayout(button_layout)

        # Card status light
        self.status_light = QLabel()
        self.status_light.setFixedSize(20, 20)
        self.status_light.setStyleSheet("background-color: red; border-radius: 10px;")
        status_layout = QHBoxLayout()
        status_layout.addWidget(QLabel("Card Status:"))
        status_layout.addWidget(self.status_light)
        self.write_layout.addLayout(status_layout)

        # Status log
        self.status_log = QTextEdit()
        self.status_log.setReadOnly(True)
        self.write_layout.addWidget(self.status_log)

        # Connect buttons
        self.write_button.clicked.connect(self.write_and_lock_url)
        self.reset_button.clicked.connect(self.reset)
        self.refresh_button.clicked.connect(self.refresh_readers)

        # Initialize reader list
        self.refresh_readers()

    def setup_read_tab(self):
        # Card status light for read tab
        self.read_status_light = QLabel()
        self.read_status_light.setFixedSize(20, 20)
        self.read_status_light.setStyleSheet("background-color: red; border-radius: 10px;")
        status_layout = QHBoxLayout()
        status_layout.addWidget(QLabel("Card Status:"))
        status_layout.addWidget(self.read_status_light)
        self.read_layout.addLayout(status_layout)


        # Read log
        self.read_log = QTextBrowser()
        self.read_log.setReadOnly(True)
        self.read_layout.addWidget(self.read_log)


    def log(self, message, is_read_log=False):
        if is_read_log:
            self.read_log.append(message)
            self.read_log.verticalScrollBar().setValue(
                self.read_log.verticalScrollBar().maximum()
            )
        else:
            self.status_log.append(message)
            self.status_log.verticalScrollBar().setValue(
                self.status_log.verticalScrollBar().maximum()
            )


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
                    self.read_status_light.setStyleSheet("background-color: green; border-radius: 10px;")
                    self.log("Card detected and ready")
                    self.log("Card detected and ready", is_read_log=True)
                    self.read_card()
            else:
                if self.card_detected:
                    self.card_detected = False
                    self.status_light.setStyleSheet("background-color: red; border-radius: 10px;")
                    self.read_status_light.setStyleSheet("background-color: red; border-radius: 10px;")

                    self.log("Card removed")
                    self.log("Card removed", is_read_log=True)
        except Exception as e:
            self.log(f"Error checking for card: {str(e)}")
            self.log(f"Error checking for card: {str(e)}", is_read_log=True)

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
            if not url.startswith(('http://', 'https://')):
                QMessageBox.warning(self, "Invalid URL", "URL must start with http:// or https://")
                return

            if not self.connect_reader():
                return

            self.log("Writing URL...")

            ndef_data = self.create_ndef_url(url)
            self.log("NDEF data: " + " ".join([hex(x) for x in ndef_data]))

            cc_data = [0xE1, 0x10, 0x6D, 0x00]
            self._write_data(3, cc_data)
            # check and rewrite the CC
            cc_check = self._read_data(3)
            if cc_check != cc_data:
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

            self.url_input.setText("https://")
            self.status_light.setStyleSheet("background-color: orange; border-radius: 10px;")
            self.log("Tag locked. You can now remove the card.")
            QMessageBox.information(self, "Success", "URL written and tag locked successfully!")

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
        self.log("Reset complete")


    def _read_data(self, page):
        apdu = [0xFF, 0xB0, 0x00, page, 0x04]
        try:
            response, sw1, sw2 = self.connection.transmit(apdu)
            if not (sw1 == 0x90 and sw2 == 0x00):
                  return None
            return response
        except Exception as e:
              self.log(f"Read exception at page {page}: {e}", is_read_log=True)
              return None


    def _decode_ndef_message(self, data):
        try:
            if not data:
                return None  # No data to decode

            index = 0

            if data[index] != 0x03:
                return None  # not a valid NDEF message

            index += 1

            length = data[index]
            index += 1
            if length == 0xFF:
                if len(data) < index + 2:
                    return None
                length = (data[index] << 8) | data[index + 1]
                index += 2


            if data[index] != 0xD1:
               return None # not an NDEF message
            index += 1

            type_length = data[index]
            index += 1


            payload_length = data[index]
            index += 1

            if len(data) < index + payload_length:
              return None

            type_field = data[index]
            index += 1

            if type_field != 0x55:
                return None  # Not a URI NDEF message type

            # now get the prefix
            prefix = data[index]
            index+=1

            url = "" # start with an empty URL and add the prefix later
            if prefix == 0x00:
                 url = ""
            elif prefix == 0x01:
                url = "http://"
            elif prefix == 0x02:
                url = "https://"
            elif prefix == 0x03:
                url = "http://www."
            elif prefix == 0x04:
                url = "https://www."
            else:
               return None

            url_bytes = data[index:index + payload_length -1] # subtract one for the prefix
            url += url_bytes.decode('utf-8')
            return url
        except Exception as e:
            self.log(f"Error decoding NDEF message: {e}", is_read_log=True)
            return None


    def read_card(self):
        try:
            if not self.connect_reader():
                self.log("Could not connect to reader for read", is_read_log=True)
                return
            self.log("Reading tag...", is_read_log=True)

            all_data = []
            for page in [3] + list(range(4, 16)):
                data = self._read_data(page)
                if data:
                   all_data.extend(data)
                else:
                    break
            
            self.log("Raw Data:" + " ".join([hex(x) for x in all_data]), is_read_log=True)

            url = self._decode_ndef_message(all_data)

            if url:
                self.log(f"URL Detected: {url}", is_read_log=True)
                webbrowser.open(url)
            else:
                self.log("No valid URL found on the tag", is_read_log=True)

        except Exception as e:
           self.log(f"Error reading card: {e}", is_read_log=True)
        finally:
             if self.connection:
                self.connection.disconnect()
https://www.microsoft.com/he-il/microsoft-copilot/microsoft-copilot-studio

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = NFCApp()
    window.show()
    sys.exit(app.exec())