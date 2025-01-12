import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QLabel, QLineEdit, QComboBox, QCheckBox, QPushButton, 
    QTextEdit, QMessageBox, QStyle)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtMultimedia import QSoundEffect
from smartcard.System import readers
from PyQt6.QtGui import QFont, QPalette, QColor

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
        self.success_sound.setSource(QUrl.fromLocalFile("beep.mp3"))
        
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
        
        # Lock checkbox
        self.lock_checkbox = QCheckBox("Lock tag after writing (Warning: This cannot be undone!)")
        self.lock_checkbox.setFont(QFont("Arial", 10))
        layout.addWidget(self.lock_checkbox)
        
        # Buttons
        button_group = QWidget()
        button_layout = QHBoxLayout(button_group)
        button_layout.setContentsMargins(0, 0, 0, 0)
        
        self.refresh_button = QPushButton("Refresh Readers")
        self.refresh_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        
        self.write_button = QPushButton("Write URL")
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
        
        # Connect signals
        self.refresh_button.clicked.connect(self.refresh_readers)
        self.write_button.clicked.connect(self.write_url)
        
        # Initial reader refresh
        self.refresh_readers()

    def log(self, message):
        self.status_log.append(message)
        self.status_log.verticalScrollBar().setValue(
            self.status_log.verticalScrollBar().maximum()
        )
    
    def refresh_readers(self):
        try:
            self.reader_combo.clear()
            for reader in readers():
                self.reader_combo.addItem(str(reader))
        except Exception as e:
            self.log(f"Error refreshing readers: {str(e)}")
    
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
            
            # Play success sound
            self.success_sound.play()
            
            # Clear URL field after successful write
            self.url_input.setText("https://")
            
            QMessageBox.information(self, "Success", 
                "URL written successfully!" + 
                (" Tag has been locked." if should_lock else ""))
            
        except Exception as e:
            self.log(f"Error: {str(e)}")

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = NFCWriterGUI()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()