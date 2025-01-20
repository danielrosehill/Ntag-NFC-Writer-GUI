from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QTextEdit, QGroupBox, QLabel, QApplication, QMessageBox, QComboBox,
    QTabWidget
)
from PyQt6.QtCore import QTimer
from smartcard.System import readers
from smartcard.Exceptions import NoCardException
import sys
import webbrowser

class NFCApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NFC URL Reader/Writer (ACR-1252)")
        self.setMinimumWidth(600)
        self.write_connection = None
        self.read_connection = None
        self.card_detected = False
        self.remaining_writes = 1

        # Create main widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Create tab widget
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # Create write tab
        write_tab = QWidget()
        write_layout = QVBoxLayout(write_tab)
        self.tab_widget.addTab(write_tab, "Write")

        # Create read tab
        read_tab = QWidget()
        read_layout = QVBoxLayout(read_tab)
        self.tab_widget.addTab(read_tab, "Read")

        # Write tab - Reader selection group
        write_reader_group = QGroupBox("ACR-1252 Reader")
        write_reader_layout = QHBoxLayout(write_reader_group)
        self.writer_combo = QComboBox()
        self.write_refresh_button = QPushButton("Refresh Readers")
        write_reader_layout.addWidget(self.writer_combo)
        write_reader_layout.addWidget(self.write_refresh_button)
        write_layout.addWidget(write_reader_group)

        # Read tab - Reader selection group
        read_reader_group = QGroupBox("ACR-1252 Reader")
        read_reader_layout = QHBoxLayout(read_reader_group)
        self.reader_combo = QComboBox()
        self.read_refresh_button = QPushButton("Refresh Readers")
        read_reader_layout.addWidget(self.reader_combo)
        read_reader_layout.addWidget(self.read_refresh_button)
        read_layout.addWidget(read_reader_group)

        # Write tab - URL input group
        url_group = QGroupBox("URL Configuration")
        url_layout = QVBoxLayout(url_group)
        self.url_input = QLineEdit()
        self.url_input.setText("https://")
        url_layout.addWidget(self.url_input)

        # Write tab - Add write counter combo box
        write_counter_layout = QHBoxLayout()
        write_counter_layout.addWidget(QLabel("Number of writes:"))
        self.write_counter_combo = QComboBox()
        self.write_counter_combo.addItems([str(i) for i in range(1, 11)])
        write_counter_layout.addWidget(self.write_counter_combo)
        url_layout.addLayout(write_counter_layout)

        # Write tab - Add remaining writes label
        self.remaining_writes_label = QLabel("Remaining writes: 1")
        url_layout.addWidget(self.remaining_writes_label)
        write_layout.addWidget(url_group)

        # Write tab - Buttons
        write_button_layout = QHBoxLayout()
        self.write_button = QPushButton("Write URL and Lock")
        self.reset_button = QPushButton("Reset")
        write_button_layout.addWidget(self.write_button)
        write_button_layout.addWidget(self.reset_button)
        write_layout.addLayout(write_button_layout)

        # Write tab - Card status light
        self.write_status_light = QLabel()
        self.write_status_light.setFixedSize(20, 20)
        self.write_status_light.setStyleSheet("background-color: red; border-radius: 10px;")
        write_status_layout = QHBoxLayout()
        write_status_layout.addWidget(QLabel("Card Status:"))
        write_status_layout.addWidget(self.write_status_light)
        write_layout.addLayout(write_status_layout)

        # Write tab - Status log
        self.write_status_log = QTextEdit()
        self.write_status_log.setReadOnly(True)
        write_layout.addWidget(self.write_status_log)

        # Read tab - Control group
        read_control_group = QGroupBox("Reader Control")
        read_control_layout = QHBoxLayout(read_control_group)
        self.read_toggle_button = QPushButton("Start Reader")
        read_control_layout.addWidget(self.read_toggle_button)
        read_layout.addWidget(read_control_group)

        # Read tab - Status
        read_status_group = QGroupBox("Tag Status")
        read_status_layout = QVBoxLayout(read_status_group)
        
        # Read tab - Card status light
        self.read_status_light = QLabel()
        self.read_status_light.setFixedSize(20, 20)
        self.read_status_light.setStyleSheet("background-color: red; border-radius: 10px;")
        read_light_layout = QHBoxLayout()
        read_light_layout.addWidget(QLabel("Card Status:"))
        read_light_layout.addWidget(self.read_status_light)
        read_status_layout.addLayout(read_light_layout)
        
        # Read tab - URL display
        self.url_display = QLineEdit()
        self.url_display.setReadOnly(True)
        read_status_layout.addWidget(QLabel("Detected URL:"))
        read_status_layout.addWidget(self.url_display)
        
        read_layout.addWidget(read_status_group)

        # Read tab - Status log
        self.read_status_log = QTextEdit()
        self.read_status_log.setReadOnly(True)
        read_layout.addWidget(self.read_status_log)

        # Timers for card detection
        self.write_card_timer = QTimer()
        self.write_card_timer.timeout.connect(self.check_for_write_card)
        self.write_card_timer.start(1000)  # Check for card every second

        self.read_card_timer = QTimer()
        self.read_card_timer.timeout.connect(self.check_for_read_card)
        self.read_card_timer.start(1000)  # Check for card every second

        # Connect buttons
        self.write_button.clicked.connect(self.write_and_lock_url)
        self.reset_button.clicked.connect(self.reset)
        self.write_refresh_button.clicked.connect(self.refresh_writers)
        self.read_refresh_button.clicked.connect(self.refresh_readers)
        self.write_counter_combo.currentTextChanged.connect(self.on_write_counter_changed)

        # Initialize state
        self.refresh_writers()
        self.refresh_readers()
        self.reader_active = False
        self.read_toggle_button.clicked.connect(self.toggle_reader)

    def write_log(self, message):
        self.write_status_log.append(message)
        self.write_status_log.verticalScrollBar().setValue(
            self.write_status_log.verticalScrollBar().maximum()
        )

    def read_log(self, message):
        self.read_status_log.append(message)
        self.read_status_log.verticalScrollBar().setValue(
            self.read_status_log.verticalScrollBar().maximum()
        )

    def on_write_counter_changed(self, value):
        self.remaining_writes = int(value)
        self.remaining_writes_label.setText(f"Remaining writes: {self.remaining_writes}")

    def refresh_writers(self):
        try:
            reader_list = readers()
            self.writer_combo.clear()
            for reader in reader_list:
                if "ACR1252" in str(reader):  # Filter for ACR-1252 readers
                    self.writer_combo.addItem(str(reader))
            if self.writer_combo.count() > 0:
                self.write_log("ACR-1252 readers refreshed successfully")
            else:
                self.write_log("No ACR-1252 readers found")
        except Exception as e:
            self.write_log(f"Error refreshing readers: {str(e)}")

    def refresh_readers(self):
        try:
            reader_list = readers()
            self.reader_combo.clear()
            for reader in reader_list:
                if "ACR1252" in str(reader):  # Filter for ACR-1252 readers
                    self.reader_combo.addItem(str(reader))
            if self.reader_combo.count() > 0:
                self.read_log("ACR-1252 readers refreshed successfully")
            else:
                self.read_log("No ACR-1252 readers found")
        except Exception as e:
            self.read_log(f"Error refreshing readers: {str(e)}")

    def check_for_write_card(self):
        try:
            if self.connect_write_reader():
                if not self.card_detected:
                    self.card_detected = True
                    self.write_status_light.setStyleSheet("background-color: green; border-radius: 10px;")
                    self.write_log("Card detected and ready")
            else:
                if self.card_detected:
                    self.card_detected = False
                    self.write_status_light.setStyleSheet("background-color: red; border-radius: 10px;")
                    self.write_log("Card removed")
        except Exception as e:
            self.write_log(f"Error checking for card: {str(e)}")

    def toggle_reader(self):
        if self.reader_active:
            self.reader_active = False
            self.read_toggle_button.setText("Start Reader")
            self.read_card_timer.stop()
            self.read_status_light.setStyleSheet("background-color: red; border-radius: 10px;")
            self.url_display.clear()
            self.read_log("Reader stopped")
        else:
            self.reader_active = True
            self.read_toggle_button.setText("Stop Reader")
            self.read_card_timer.start()
            self.read_log("Reader started")

    def check_for_read_card(self):
        if not self.reader_active:
            return
            
        try:
            if self.connect_read_reader():
                self.read_status_light.setStyleSheet("background-color: green; border-radius: 10px;")
                self.read_tag()
            else:
                self.read_status_light.setStyleSheet("background-color: red; border-radius: 10px;")
                self.url_display.clear()
        except Exception as e:
            self.read_log(f"Error checking for card: {str(e)}")

    def connect_write_reader(self):
        try:
            if not self.writer_combo.currentText():
                return False
            r = readers()
            self.writer = [reader for reader in r if str(reader) == self.writer_combo.currentText()][0]
            self.write_connection = self.writer.createConnection()
            self.write_connection.connect()
            return True
        except Exception as e:
            return False

    def connect_read_reader(self):
        try:
            if not self.reader_combo.currentText():
                return False
            r = readers()
            self.reader = [reader for reader in r if str(reader) == self.reader_combo.currentText()][0]
            self.read_connection = self.reader.createConnection()
            self.read_connection.connect()
            return True
        except Exception as e:
            return False

    def _write_data(self, page, data):
        while len(data) < 4:
            data.append(0x00)
        apdu = [0xFF, 0xD6, 0x00, page] + [len(data)] + data
        response, sw1, sw2 = self.write_connection.transmit(apdu)
        if not (sw1 == 0x90 and sw2 == 0x00):
            raise Exception(f"Write failed at page {page}: {hex(sw1)} {hex(sw2)}")

    def _read_data(self, page):
        apdu = [0xFF, 0xB0, 0x00, page, 0x04]
        response, sw1, sw2 = self.read_connection.transmit(apdu)
        if not (sw1 == 0x90 and sw2 == 0x00):
            raise Exception(f"Read failed at page {page}: {hex(sw1)} {hex(sw2)}")
        return response

    def read_tag(self):
        try:
            # Read capability container
            cc = self._read_data(3)
            if cc[0] != 0xE1:  # Check if tag is NDEF formatted
                self.read_log("Tag is not NDEF formatted")
                return

            # Read first page to get length
            first_chunk = self._read_data(4)
            self.read_log(f"First page data: {' '.join([hex(x) for x in first_chunk])}")
            
            # Skip proprietary header and find NDEF message
            # First byte (0x01) is proprietary, followed by NDEF TLV (0x03)
            if first_chunk[1] != 0x03:  # NDEF message TLV tag
                self.read_log(f"NDEF TLV tag not found where expected")
                return

            # Read data page by page until we find the NDEF record and terminator
            ndef_data = first_chunk
            found_d1 = False
            current_page = 5  # Start from page 5 since we already have page 4
            
            while current_page <= 39:  # NTAG215 has 40 pages (0-39) with last page reserved for lock bytes
                chunk = self._read_data(current_page)
                self.read_log(f"Read page {current_page}: {' '.join([hex(x) for x in chunk])}")
                ndef_data.extend(chunk)
                
                # Check if we found the NDEF record header (0xD1)
                if not found_d1 and 0xD1 in chunk:
                    found_d1 = True
                
                # If we found the terminator after finding 0xD1, we're done
                if found_d1 and 0xFE in chunk:
                    break
                    
                current_page += 1
            
            # Trim data at terminator
            if 0xFE in ndef_data:
                terminator_index = ndef_data.index(0xFE)
                ndef_data = ndef_data[:terminator_index + 1]
            
            self.read_log(f"Trimmed NDEF data: {' '.join([hex(x) for x in ndef_data])}")

            # Find NDEF record in the data (should start with 0xD1)
            ndef_start = 3  # NDEF record starts after TLV tag and length
            if ndef_data[ndef_start] != 0xD1:  # NDEF header (MB=1, ME=1, SR=1, TNF=1)
                self.read_log(f"Invalid NDEF header: {hex(ndef_data[ndef_start])}")
                return

            self.read_log(f"Found NDEF record at offset: {ndef_start}")

            # Parse record header
            type_length = ndef_data[ndef_start + 1]
            payload_length = ndef_data[ndef_start + 2]
            record_offset = ndef_start + 3

            self.read_log(f"Type length: {type_length}, Payload length: {payload_length}")

            # Verify URI record type
            if ndef_data[record_offset] != 0x55:  # 'U' type
                self.read_log(f"Not a URI record: {hex(ndef_data[record_offset])}")
                return

            # Get URL prefix and data
            prefix_code = ndef_data[record_offset + 1]
            url_start = record_offset + 2

            self.read_log(f"URL prefix code: {hex(prefix_code)}")

            # Handle different URL prefixes
            prefix_map = {
                0x00: "",           # No prefix
                0x01: "http://www.",
                0x02: "https://www.",
                0x03: "http://",
                0x04: "https://"
            }
            
            if prefix_code in prefix_map:
                # URL length is payload_length - 1 (subtract prefix byte)
                url_bytes = ndef_data[url_start:url_start + payload_length - 1]
                url = prefix_map[prefix_code] + bytes(url_bytes).decode('utf-8')
                
                self.read_log(f"Extracted URL bytes: {' '.join([hex(x) for x in url_bytes])}")
                
                if self.url_display.text() != url:
                    self.url_display.setText(url)
                    self.read_log(f"URL detected: {url}")
                    webbrowser.get('google-chrome').open(url)
            else:
                self.read_log(f"Unsupported URL prefix code: {hex(prefix_code)}")

        except Exception as e:
            self.read_log(f"Error reading tag: {str(e)}")

    def create_ndef_url(self, url):
        url = url.lower().replace('https://', '').replace('http://', '')
        url_bytes = url.encode()
        url_length = len(url_bytes)
        
        # Calculate total NDEF message length (including all headers)
        ndef_length = url_length + 5  # URL + NDEF header(1) + type length(1) + payload length(1) + type(1) + prefix(1)
        
        # Use extended length format for larger payloads
        if ndef_length > 254:
            message = [
                0x01,  # Proprietary header
                0x03,  # NDEF message TLV tag
                0xFF,  # Extended length marker
                (ndef_length >> 8) & 0xFF,  # Length high byte
                ndef_length & 0xFF,         # Length low byte
                0xD1,  # NDEF header (MB=1, ME=1, SR=1, TNF=1)
                0x01,  # Type length (1 byte for 'U')
                url_length + 1,  # Payload length (URL + prefix byte)
                0x55,  # 'U' type
                0x04,  # https:// prefix
            ]
        else:
            message = [
                0x01,  # Proprietary header
                0x03,  # NDEF message TLV tag
                ndef_length,  # Length
                0xD1,  # NDEF header (MB=1, ME=1, SR=1, TNF=1)
                0x01,  # Type length (1 byte for 'U')
                url_length + 1,  # Payload length (URL + prefix byte)
                0x55,  # 'U' type
                0x04,  # https:// prefix
            ]
        
        # Add URL and terminator
        message.extend(url_bytes)
        message.append(0xFE)  # TLV terminator
        
        return message

    def lock_tag(self):
        try:
            static_lock_bytes = [0xFF, 0xFF, 0xFF, 0xFF]
            self._write_data(2, static_lock_bytes)

            dynamic_lock_bytes = [0xFF, 0xFF, 0xFF, 0xFF]
            self._write_data(40, dynamic_lock_bytes)

            self.write_log("Tag locked successfully")
        except Exception as e:
            self.write_log(f"Warning: Could not lock tag - {str(e)}")

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

            if not self.connect_write_reader():
                return

            if self.remaining_writes <= 0:
                self.reset()
                QMessageBox.warning(self, "Write Limit Reached", "Maximum number of writes reached. Settings have been reset.")
                return

            self.write_log("Writing URL...")

            ndef_data = self.create_ndef_url(url)
            self.write_log("NDEF data: " + " ".join([hex(x) for x in ndef_data]))

            cc_data = [0xE1, 0x10, 0x6D, 0x00]
            self._write_data(3, cc_data)

            page = 4
            chunk_size = 4
            for i in range(0, len(ndef_data), chunk_size):
                chunk = ndef_data[i:i + chunk_size]
                self._write_data(page, chunk)
                page += 1

                if page > 39:  # NTAG215 has 40 pages (0-39) with last page reserved for lock bytes
                    raise Exception("URL too long for tag capacity")

            self.lock_tag()

            # Update remaining writes counter
            self.remaining_writes -= 1
            self.remaining_writes_label.setText(f"Remaining writes: {self.remaining_writes}")

            if self.remaining_writes > 0:
                self.write_status_light.setStyleSheet("background-color: orange; border-radius: 10px;")
                self.write_log("Tag locked. You can now remove the card.")
                QMessageBox.information(self, "Success", f"URL written and tag locked successfully! {self.remaining_writes} writes remaining.")
            else:
                self.reset()
                QMessageBox.information(self, "Success", "URL written and tag locked successfully! Maximum writes reached, settings reset.")

        except Exception as e:
            self.write_log(f"Error: {str(e)}")
            QMessageBox.critical(self, "Error", str(e))
        finally:
            if self.write_connection:
                self.write_connection.disconnect()

    def reset(self):
        self.url_input.setText("https://")
        self.write_status_log.clear()
        self.card_detected = False
        self.write_status_light.setStyleSheet("background-color: red; border-radius: 10px;")
        self.remaining_writes = int(self.write_counter_combo.currentText())
        self.remaining_writes_label.setText(f"Remaining writes: {self.remaining_writes}")
        self.write_log("Reset complete")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = NFCApp()
    window.show()
    sys.exit(app.exec())
