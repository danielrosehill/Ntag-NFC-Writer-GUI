from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLineEdit, QComboBox, QPushButton, QTextEdit, QGroupBox, QTabWidget,
    QLabel, QApplication, QMessageBox)
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

    def setup_reader_tab(self):
        reader_widget = QWidget()
        layout = QVBoxLayout(reader_widget)
        
        # Read button and status
        read_button = QPushButton("Read Tag")
        self.read_status = QLabel("Ready to read...")
        layout.addWidget(read_button)
        layout.addWidget(self.read_status)
        
        read_button.clicked.connect(self.read_tag)
        self.tab_widget.addTab(reader_widget, "Read URL")

    def setup_writer_tab(self):
        writer_widget = QWidget()
        layout = QVBoxLayout(writer_widget)
        
        # URL input
        url_group = QGroupBox("URL Configuration")
        url_layout = QVBoxLayout(url_group)
        self.url_input = QLineEdit()
        self.url_input.setText("https://")
        url_layout.addWidget(self.url_input)
        layout.addWidget(url_group)
        
        # Write button
        write_button = QPushButton("Write URL and Lock")
        layout.addWidget(write_button)
        
        write_button.clicked.connect(self.write_and_lock_url)
        self.tab_widget.addTab(writer_widget, "Write URL")

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
            static_lock_bytes = [0xFF, 0xFF, 0xFF, 0xFF]
            self._write_data(2, static_lock_bytes)
            
            # Set dynamic lock bytes (page 40)
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
            
            # Write CC (Capability Container)
            cc_data = [0xE1, 0x10, 0x6D, 0x00]
            self._write_data(3, cc_data)
            
            # Write NDEF message in chunks
            page = 4
            chunk_size = 4
            for i in range(0, len(ndef_data), chunk_size):
                chunk = ndef_data[i:i+chunk_size]
                self._write_data(page, chunk)
                page += 1
            
            # Lock the tag
            self.lock_tag()
            
            self.url_input.setText("https://")
            QMessageBox.information(self, "Success", "URL written and tag locked successfully!")
            
        except Exception as e:
            self.log(f"Error: {str(e)}")
            QMessageBox.critical(self, "Error", str(e))
        finally:
            if self.connection:
                self.connection.disconnect()

    def read_tag(self):
        try:
            if not self.connect_reader():
                return
                
            # Read capability container
            apdu = [0xFF, 0xB0, 0x00, 3, 4]
            response, sw1, sw2 = self.connection.transmit(apdu)
            if not (sw1 == 0x90 and sw2 == 0x00):
                raise Exception("Failed to read capability container")
                
            # Read NDEF data
            data = []
            for page in range(4, 12):  # Read more pages
                apdu = [0xFF, 0xB0, 0x00, page, 4]
                response, sw1, sw2 = self.connection.transmit(apdu)
                if sw1 == 0x90 and sw2 == 0x00:
                    data.extend(response)
                else:
                    break
            
            url = self.parse_ndef_message(data)
            if url:
                self.read_status.setText(f"Found URL: {url}")
                self.log(f"URL found: {url}")
                if QMessageBox.question(self, "Open URL", 
                    f"Do you want to open {url}?") == QMessageBox.StandardButton.Yes:
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
            if data[0] == 0x03:  # NDEF message TLV tag
                length = data[1]
                if data[5] == 0x55:  # URI record type
                    url_start = 7  # URL starts after NDEF header
                    url_bytes = data[url_start:url_start + length - 5]
                    # Filter out padding bytes
                    url_bytes = [b for b in url_bytes if b != 0x00]
                    return "https://" + bytes(url_bytes).decode('utf-8')
            return None
        except Exception:
            return None

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

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = NFCApp()
    window.show()
    sys.exit(app.exec())