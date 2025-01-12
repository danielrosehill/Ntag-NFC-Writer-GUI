import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QLineEdit, QComboBox, 
                            QPushButton, QTextEdit, QMessageBox, QCheckBox)
from PyQt6.QtCore import Qt
from smartcard.System import readers
from smartcard.util import toBytes, toHexString

class NFCWriterGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NFC URL Writer")
        self.setMinimumWidth(600)
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # URL input
        url_layout = QHBoxLayout()
        url_label = QLabel("URL:")
        self.url_input = QLineEdit()
        self.url_input.setText("https://")
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input)
        layout.addLayout(url_layout)
        
        # Reader selection
        reader_layout = QHBoxLayout()
        reader_label = QLabel("Reader:")
        self.reader_combo = QComboBox()
        reader_layout.addWidget(reader_label)
        reader_layout.addWidget(self.reader_combo)
        layout.addLayout(reader_layout)
        
        # Lock checkbox
        self.lock_checkbox = QCheckBox("Lock tag after writing")
        layout.addWidget(self.lock_checkbox)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh Readers")
        self.write_button = QPushButton("Write URL")
        button_layout.addWidget(self.refresh_button)
        button_layout.addWidget(self.write_button)
        layout.addLayout(button_layout)
        
        # Status log
        self.status_log = QTextEdit()
        self.status_log.setReadOnly(True)
        layout.addWidget(self.status_log)
        
        # Connect signals
        self.refresh_button.clicked.connect(self.refresh_readers)
        self.write_button.clicked.connect(self.write_url)
        
        # Initialize readers
        self.refresh_readers()
    
    def log(self, message):
        self.status_log.append(message)
    
    def refresh_readers(self):
        try:
            r = readers()
            self.reader_combo.clear()
            for reader in r:
                self.reader_combo.addItem(str(reader))
            self.log("Readers refreshed: " + ", ".join([str(r) for r in readers()]))
        except Exception as e:
            self.log(f"Error refreshing readers: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to refresh readers: {str(e)}")
    
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
    
    def lock_tag(self, connection):
        try:
            # Lock pages 3-15
            lock_command = [0xFF, 0xD6, 0x00, 0x02, 0x04, 0x00, 0x00, 0xF0, 0xFF]
            response, sw1, sw2 = connection.transmit(lock_command)
            self.log(f"Lock status: {hex(sw1)} {hex(sw2)}")
            return sw1 == 0x90
        except Exception as e:
            self.log(f"Error locking tag: {str(e)}")
            return False

    def write_url(self):
        try:
            url = self.url_input.text()
            if not url.startswith(('http://', 'https://')):
                QMessageBox.warning(self, "Invalid URL", "URL must start with http:// or https://")
                return
            
            if self.reader_combo.currentText() == "":
                QMessageBox.warning(self, "No Reader", "No NFC reader selected")
                return
            
            # Confirm if locking is selected
            should_lock = self.lock_checkbox.isChecked()
            if should_lock:
                reply = QMessageBox.warning(self, "Confirm Lock",
                    "Are you sure you want to lock the tag? This cannot be undone!",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No)
                
                if reply == QMessageBox.StandardButton.No:
                    return
            
            r = readers()
            reader = [reader for reader in r if str(reader) == self.reader_combo.currentText()][0]
            
            connection = reader.createConnection()
            connection.connect()
            
            self.log(f"Connected to: {reader}")
            self.log(f"Writing URL: {url}")
            
            ndef_data = self.create_ndef_url(url)
            self.log("NDEF data: " + " ".join([hex(x) for x in ndef_data]))
            
            # Write CC
            cc_data = [0xE1, 0x10, 0x6D, 0x00]
            apdu = [0xFF, 0xD6, 0x00, 0x03] + [len(cc_data)] + cc_data
            response, sw1, sw2 = connection.transmit(apdu)
            self.log(f"CC write status: {hex(sw1)} {hex(sw2)}")
            
            # Write NDEF data in chunks
            page = 4
            chunk_size = 4
            for i in range(0, len(ndef_data), chunk_size):
                chunk = ndef_data[i:i+chunk_size]
                while len(chunk) < chunk_size:
                    chunk.append(0x00)
                apdu = [0xFF, 0xD6, 0x00, page] + [len(chunk)] + chunk
                response, sw1, sw2 = connection.transmit(apdu)
                self.log(f"Data write status page {page}: {hex(sw1)} {hex(sw2)}")
                page += 1
            
            # Lock tag if requested
            if should_lock:
                if self.lock_tag(connection):
                    self.log("Tag locked successfully")
                else:
                    QMessageBox.warning(self, "Lock Warning", "Failed to lock the tag!")
            
            # Clear URL field after successful write
            self.url_input.setText("https://")
            
            QMessageBox.information(self, "Success", 
                "URL written successfully!" + 
                (" Tag has been locked." if should_lock else ""))
            
        except Exception as e:
            self.log(f"Error: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to write URL: {str(e)}")

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Use Fusion style for a modern look
    window = NFCWriterGUI()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()