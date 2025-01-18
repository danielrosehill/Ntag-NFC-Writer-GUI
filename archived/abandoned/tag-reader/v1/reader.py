from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QTextEdit, 
    QLabel, QApplication, QComboBox, QPushButton, QGroupBox, QHBoxLayout)
from PyQt6.QtCore import QTimer
from smartcard.System import readers
from smartcard.Exceptions import NoCardException
import sys
import webbrowser

class NFCReaderGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NFC URL Reader")
        self.setMinimumWidth(400)
        self.connection = None
        self.tag_present = False
        self.last_read_url = None
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Reader selection group
        reader_group = QGroupBox("NFC Reader")
        reader_layout = QHBoxLayout(reader_group)
        self.reader_combo = QComboBox()
        self.refresh_button = QPushButton("Refresh Readers")
        reader_layout.addWidget(self.reader_combo)
        reader_layout.addWidget(self.refresh_button)
        layout.addWidget(reader_group)
        
        # Status indicator
        self.status_label = QLabel("Waiting for NFC tag...")
        layout.addWidget(self.status_label)
        
        # Presence Indicator
        self.presence_indicator = QLabel()
        self.presence_indicator.setFixedSize(20, 20)
        self.presence_indicator.setStyleSheet("background-color: gray; border-radius: 10px;")
        layout.addWidget(self.presence_indicator)
        
        # Log display
        self.status_log = QTextEdit()
        self.status_log.setReadOnly(True)
        layout.addWidget(self.status_log)
        
        # Connect buttons
        self.refresh_button.clicked.connect(self.refresh_readers)
        
        # Start the tag detection timer
        self.tag_timer = QTimer()
        self.tag_timer.timeout.connect(self.check_and_read_tag)
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

    def get_selected_reader(self):
        try:
            if self.reader_combo.currentText():
                reader_list = readers()
                selected_reader = [r for r in reader_list 
                                 if str(r) == self.reader_combo.currentText()]
                if selected_reader:
                    return selected_reader[0]
            return None
        except Exception as e:
            self.log(f"Error getting reader: {str(e)}")
            return None

    def read_tag(self):
        try:
            reader = self.get_selected_reader()
            if not reader:
                return None
                
            connection = reader.createConnection()
            connection.connect()
            
            # Read NDEF message
            apdu = [0xFF, 0xB0, 0x00, 4, 16]  # Read 16 bytes starting from page 4
            response, sw1, sw2 = connection.transmit(apdu)
            
            if sw1 == 0x90 and sw2 == 0x00:
                # Parse NDEF message
                if response[0] == 0x03:  # NDEF message TLV tag
                    length = response[1]
                    if response[5] == 0x55:  # URI record type
                        url_prefix = "https://"  # Default prefix
                        url_start = 7  # URL starts after NDEF header
                        url_bytes = response[url_start:url_start + length - 5]
                        url = url_prefix + bytes(url_bytes).decode('utf-8')
                        return url
            
            connection.disconnect()
            return None
            
        except Exception as e:
            self.log(f"Error reading tag: {str(e)}")
            return None

    def check_and_read_tag(self):
        if not self.reader_combo.currentText():
            self.presence_indicator.setStyleSheet("background-color: gray; border-radius: 10px;")
            self.status_label.setText("No reader selected")
            return

        try:
            url = self.read_tag()
            if url:
                self.presence_indicator.setStyleSheet("background-color: green; border-radius: 10px;")
                if url != self.last_read_url:
                    self.last_read_url = url
                    self.log(f"Opening URL: {url}")
                    webbrowser.open(url)
                    self.status_label.setText(f"Last read URL: {url}")
            else:
                self.presence_indicator.setStyleSheet("background-color: gray; border-radius: 10px;")
                self.last_read_url = None
                self.status_label.setText("Waiting for NFC tag...")
                
        except Exception as e:
            self.presence_indicator.setStyleSheet("background-color: gray; border-radius: 10px;")
            self.last_read_url = None
            self.log(f"Error: {str(e)}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = NFCReaderGUI()
    window.show()
    sys.exit(app.exec())