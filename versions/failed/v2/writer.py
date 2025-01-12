import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QLabel, QLineEdit, QComboBox, QPushButton, 
    QTextEdit, QMessageBox, QStyle, QFrame)
from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtMultimedia import QSoundEffect
from smartcard.System import readers
from smartcard.Exceptions import CardConnectionException
from PyQt6.QtGui import QFont, QColor

class CardPresenceIndicator(QFrame):
    def __init__(self):
        super().__init__()
        self.setFixedSize(20, 20)
        self.setFrameShape(QFrame.Shape.Box)
        self.setFrameShadow(QFrame.Shadow.Plain)
        self.setState(False)
        
    def setState(self, is_present):
        if is_present:
            self.setStyleSheet("""
                QFrame {
                    background-color: #2ECC71;
                    border-radius: 10px;
                    border: 1px solid #27AE60;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame {
                    background-color: #E74C3C;
                    border-radius: 10px;
                    border: 1px solid #C0392B;
                }
            """)

class NFCWriterGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NFC URL Writer")
        self.setMinimumWidth(800)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            QPushButton {
                background-color: #0078D7;
                color: white;
                padding: 8px 15px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1084E3;
            }
            QLineEdit, QComboBox {
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: white;
            }
            QTextEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: white;
            }
        """)
        
        # Initialize sound effect
        self.success_sound = QSoundEffect()
        self.success_sound.setSource(QUrl.fromLocalFile("success.wav"))
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title_label = QLabel("NFC URL Writer")
        title_label.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # URL input
        url_group = QWidget()
        url_layout = QHBoxLayout(url_group)
        url_layout.setContentsMargins(0, 0, 0, 0)
        url_label = QLabel("URL:")
        url_label.setFont(QFont("Arial", 10))
        self.url_input = QLineEdit()
        self.url_input.setText("https://")
        self.url_input.setMinimumWidth(400)
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input)
        layout.addWidget(url_group)
        
        # Reader selection
        reader_group = QWidget()
        reader_layout = QHBoxLayout(reader_group)
        reader_layout.setContentsMargins(0, 0, 0, 0)
        reader_label = QLabel("Reader:")
        reader_label.setFont(QFont("Arial", 10))
        self.reader_combo = QComboBox()
        self.reader_combo.setMinimumWidth(400)
        reader_layout.addWidget(reader_label)
        reader_layout.addWidget(self.reader_combo)
        layout.addWidget(reader_group)
        
        # Buttons
        button_group = QWidget()
        button_layout = QHBoxLayout(button_group)
        button_layout.setContentsMargins(0, 0, 0, 0)
        
        self.refresh_button = QPushButton("Refresh Readers")
        self.refresh_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        
        self.write_button = QPushButton("Write and Lock")
        self.write_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        
        button_layout.addWidget(self.refresh_button)
        button_layout.addWidget(self.write_button)
        layout.addWidget(button_group)
        
        # Status log
        log_label = QLabel("Status Log:")
        log_label.setFont(QFont("Arial", 10))
        layout.addWidget(log_label)
        
        self.status_log = QTextEdit()
        self.status_log.setReadOnly(True)
        self.status_log.setMaximumHeight(150)
        self.status_log.setFont(QFont("Consolas", 9))
        layout.addWidget(self.status_log)
        
        # Card presence indicator
        indicator_widget = QWidget()
        indicator_layout = QHBoxLayout(indicator_widget)
        indicator_layout.setContentsMargins(0, 0, 0, 0)
        
        self.card_indicator = CardPresenceIndicator()
        indicator_label = QLabel("Card Present")
        indicator_label.setFont(QFont("Arial", 10))
        
        indicator_layout.addWidget(self.card_indicator)
        indicator_layout.addWidget(indicator_label)
        indicator_layout.addStretch()
        layout.addWidget(indicator_widget)
        
        # Connect signals
        self.refresh_button.clicked.connect(self.refresh_readers)
        self.write_button.clicked.connect(self.write_url)
        
        # Setup card detection timer
        self.check_timer = QTimer()
        self.check_timer.timeout.connect(self.check_card_presence)
        self.check_timer.start(500)  # Check every 500ms
        
        # Initial reader refresh
        self.refresh_readers()

    def check_card_presence(self):
        try:
            if self.reader_combo.currentText():
                r = readers()
                reader = [reader for reader in r if str(reader) == self.reader_combo.currentText()][0]
                connection = reader.createConnection()
                connection.connect()
                self.card_indicator.setState(True)
                connection.disconnect()
            else:
                self.card_indicator.setState(False)
        except:
            self.card_indicator.setState(False)

    def log(self, message):
        self.status_log.append(message)
        self.status_log.verticalScrollBar().setValue(
            self.status_log.verticalScrollBar().maximum()
        )

    def refresh_readers(self):
        try:
            self.reader_combo.clear()
            r = readers()
            for reader in r:
                self.reader_combo.addItem(str(reader))
            self.log("Readers refreshed successfully")
        except Exception as e:
            self.log(f"Error refreshing readers: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to refresh readers: {str(e)}")

    def create_ndef_url(self, url):
        """Create NDEF message for URL."""
        # URL prefix codes
        prefix_map = {
            'http://www.': 0x01,
            'https://www.': 0x02,
            'http://': 0x03,
            'https://': 0x04,
        }
        
        # Find matching prefix
        prefix_code = 0x00
        for prefix, code in prefix_map.items():
            if url.startswith(prefix):
                prefix_code = code
                url = url[len(prefix):]
                break
        
        # Convert URL to bytes
        url_bytes = url.encode('utf-8')
        
        # Create NDEF record
        ndef_record = [
            0xD1,                # TNF + Flags (MB=1, ME=1, SR=1)
            0x01,                # Type Length
            len(url_bytes) + 1,  # Payload Length (including prefix byte)
            ord('U'),            # Type ('U' for URL)
            prefix_code          # URL Prefix
        ] + list(url_bytes)      # URL without prefix
        
        # Create NDEF message
        ndef_message = [len(ndef_record)] + ndef_record + [0xFE]
        
        return ndef_message

    def lock_tag(self, connection):
        try:
            # Lock bytes for NTAG21x
            lock_bytes = [0x01, 0x00, 0x0F, 0xBD]
            apdu = [0xFF, 0xD6, 0x00, 0x02] + [len(lock_bytes)] + lock_bytes
            response, sw1, sw2 = connection.transmit(apdu)
            return sw1 == 0x90 and sw2 == 0x00
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
            
            # Lock tag
            if self.lock_tag(connection):
                self.log("Tag locked successfully")
            else:
                QMessageBox.warning(self, "Lock Warning", "Failed to lock the tag!")
            
            # Play success sound
            self.success_sound.play()
            
            # Clear URL field after successful write
            self.url_input.setText("https://")
            
            QMessageBox.information(self, "Success", "URL written and tag locked successfully!")
            
        except Exception as e:
            self.log(f"Error: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to write URL: {str(e)}")

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = NFCWriterGUI()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()