from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLineEdit, QComboBox, QPushButton, QTextEdit, QGroupBox, QTabWidget,
    QLabel, QApplication, QMessageBox)
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor
from smartcard.System import readers
from smartcard.Exceptions import NoCardException
import webbrowser
import sys

class NFCApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NFC URL Reader/Writer")
        self.setMinimumWidth(600)
        self.connection = None
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Common reader selection group
        reader_group = QGroupBox("NFC Reader")
        reader_layout = QHBoxLayout(reader_group)
        self.reader_combo = QComboBox()
        self.refresh_button = QPushButton("Refresh Readers")
        reader_layout.addWidget(self.reader_combo)
        reader_layout.addWidget(self.refresh_button)
        layout.addWidget(reader_group)
        
        # Tab widget for read/write modes
        self.tab_widget = QTabWidget()
        self.setup_reader_tab()
        self.setup_writer_tab()
        layout.addWidget(self.tab_widget)
        
        # Status log at bottom
        self.status_log = QTextEdit()
        self.status_log.setReadOnly(True)
        layout.addWidget(self.status_log)
        
        # Connect buttons
        self.refresh_button.clicked.connect(self.refresh_readers)
        self.refresh_readers()

    def log(self, message):
        self.status_log.append(message)
        self.status_log.verticalScrollBar().setValue(
            self.status_log.verticalScrollBar().maximum())

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

    def connect_reader(self):
        if not self.reader_combo.currentText():
            QMessageBox.warning(self, "No Reader", "Please select an NFC reader")
            return False
            
        try:
            r = readers()
            self.reader = [reader for reader in r 
                          if str(reader) == self.reader_combo.currentText()][0]
            self.connection = self.reader.createConnection()
            self.connection.connect()
            return True
        except Exception as e:
            self.log(f"Error connecting to reader: {str(e)}")
            return False

    def _write_data(self, page, data):
        while len(data) < 4:
            data.append(0x00)
        apdu = [0xFF, 0xD6, 0x00, page] + [len(data)] + data
        response, sw1, sw2 = self.connection.transmit(apdu)
        if not (sw1 == 0x90 and sw2 == 0x00):
            raise Exception(f"Write failed at page {page}: {hex(sw1)} {hex(sw2)}")

    def setup_reader_tab(self):
        reader_widget = QWidget()
        layout = QVBoxLayout(reader_widget)
        
        read_button = QPushButton("Read Tag")
        self.read_status = QLabel("Ready to read...")
        layout.addWidget(read_button)
        layout.addWidget(self.read_status)
        
        read_button.clicked.connect(self.read_tag)
        self.tab_widget.addTab(reader_widget, "Read URL")

    def setup_writer_tab(self):
        writer_widget = QWidget()
        layout = QVBoxLayout(writer_widget)
        
        url_group = QGroupBox("URL Configuration")
        url_layout = QVBoxLayout(url_group)
        self.url_input = QLineEdit()
        self.url_input.setText("https://")
        url_layout.addWidget(self.url_input)
        layout.addWidget(url_group)
        
        write_button = QPushButton("Write URL and Lock")
        layout.addWidget(write_button)
        
        write_button.clicked.connect(self.write_and_lock_url)
        self.tab_widget.addTab(writer_widget, "Write URL")

    def read_tag(self):
        try:
            if not self.connect_reader():
                return
                
            # Read capability container
            apdu = [0xFF, 0xB0, 0x00, 3, 4]
            response, sw1, sw2 = self.connection.transmit(apdu)
            if not (sw1 == 0x90 and sw2 == 0x00):
                raise Exception("Failed to read capability container")
                
            # Read NDEF data with improved error handling
            data = []
            max_page = 63  # Increased maximum pages to read
            consecutive_errors = 0
            
            for page in range(4, max_page):
                try:
                    apdu = [0xFF, 0xB0, 0x00, page, 4]
                    response, sw1, sw2 = self.connection.transmit(apdu)
                    
                    if sw1 == 0x90 and sw2 == 0x00:
                        data.extend(response)
                        consecutive_errors = 0
                    else:
                        consecutive_errors += 1
                        if consecutive_errors >= 3:  # Stop after 3 consecutive errors
                            break
                except Exception:
                    consecutive_errors += 1
                    if consecutive_errors >= 3:
                        break
                    continue
            
            url = self.parse_ndef_message(data)
            if url:
                self.read_status.setText(f"Found URL: {url}")
                self.log(f"URL found: {url}")
                webbrowser.open(url)
            else:
                self.read_status.setText("No URL found or invalid tag format")
                
        except Exception as e:
            self.log(f"Error reading tag: {str(e)}")
            self.read_status.setText(f"Error: {str(e)}")
        finally:
            if self.connection:
                self.connection.disconnect()

    def parse_ndef_message(self, data):
        try:
            if not data or len(data) < 2:
                return None
                
            # Find NDEF message TLV
            i = 0
            while i < len(data):
                if data[i] == 0x03:  # NDEF message TLV
                    i += 1
                    # Handle length
                    if i >= len(data):
                        return None
                        
                    length = data[i]
                    if length == 0xFF and i + 2 < len(data):  # Extended length
                        length = (data[i + 1] << 8) + data[i + 2]
                        i += 3
                    else:
                        i += 1
                        
                    # Process NDEF record
                    if i + 2 >= len(data):
                        return None
                        
                    record_header = data[i]
                    type_length = data[i + 1]
                    
                    if i + type_length + 2 >= len(data):
                        return None
                        
                    # Check for URI record
                    if data[i + 2:i + 2 + type_length] == [0x55]:  # 'U' type
                        payload_length = data[i + 2 + type_length]
                        if i + 2 + type_length + payload_length >= len(data):
                            return None
                            
                        prefix_id = data[i + 2 + type_length + 1]
                        url_bytes = data[i + 2 + type_length + 2:i + 2 + type_length + payload_length]
                        
                        # Handle URL prefixes
                        prefixes = {
                            0x01: "http://www.",
                            0x02: "https://www.",
                            0x03: "http://",
                            0x04: "https://",
                            0x05: "tel:",
                            0x06: "mailto:",
                        }
                        
                        prefix = prefixes.get(prefix_id, "")
                        try:
                            url = prefix + bytes(url_bytes).decode('utf-8', errors='ignore')
                            return url
                        except Exception:
                            return None
                            
                i += 1
            return None
            
        except Exception as e:
            self.log(f"Error parsing NDEF: {str(e)}")
            return None

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
        try:
            url = self.url_input.text()
            if not url.startswith(('http://', 'https://')):
                QMessageBox.warning(self, "Invalid URL", "URL must start with http:// or https://")
                return
            
            if not self.connect_reader():
                return
            
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
                
                if page > 35:
                    raise Exception("URL too long for tag capacity")
            
            self.lock_tag()
            
            self.url_input.setText("https://")
            QMessageBox.information(self, "Success", "URL written and tag locked successfully!")
            
        except Exception as e:
            self.log(f"Error: {str(e)}")
            QMessageBox.critical(self, "Error", str(e))
        finally:
            if self.connection:
                self.connection.disconnect()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = NFCApp()
    window.show()
    sys.exit(app.exec())