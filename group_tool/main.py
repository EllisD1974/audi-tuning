import sys
import os
import json
import subprocess
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QPushButton, QTextEdit, QFileDialog, QMessageBox, QListWidget,
    QFileIconProvider, QListWidgetItem, QInputDialog, QCheckBox,
    QDialog, QDialogButtonBox, QFormLayout, QMenu
)
from PyQt5.QtCore import QProcess, QFileInfo, Qt


CONFIG_FILE = "apps_config.json"


def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


class WorkflowLauncher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Workflow Launcher")
        self.resize(700, 500)

        self.config = self.load_config()

        # Main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.layout = QVBoxLayout(central_widget)

        # List view for apps
        self.app_list = QListWidget()
        self.populate_app_list()
        self.app_list.itemDoubleClicked.connect(self.launch_selected_app)
        self.app_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.app_list.customContextMenuRequested.connect(self.show_context_menu)
        self.layout.addWidget(self.app_list)

        # Button to launch selected app
        self.launch_button = QPushButton("Launch Selected App")
        self.launch_button.clicked.connect(self.launch_selected_app)
        self.layout.addWidget(self.launch_button)

        # Button to add new app
        self.add_button = QPushButton("Add Application")
        self.add_button.clicked.connect(self.add_application)
        self.layout.addWidget(self.add_button)

        # Output area (for CLI tools)
        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        self.layout.addWidget(self.output_area)

        self.process = None

    def populate_app_list(self):
        """Fill the list with apps + icons if available."""
        self.app_list.clear()
        icon_provider = QFileIconProvider()

        for key, app_info in self.config.items():
            path = app_info.get("path")
            item = QListWidgetItem(key)

            if path and os.path.exists(path):
                # Try to get system icon for the executable
                icon = icon_provider.icon(QFileInfo(path))
                item.setIcon(icon)
            else:
                # Generic "missing" icon
                item.setIcon(self.style().standardIcon(QApplication.style().SP_MessageBoxWarning))

            self.app_list.addItem(item)

    def load_config(self):
        """Load app config, or return empty dict."""
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        return {}

    def save_config(self):
        """Save current config to file and refresh list."""
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.config, f, indent=4)
        self.populate_app_list()

    def get_app_info(self, key):
        """Ensure app info exists and has a valid path."""
        app_info = self.config.get(key, {})
        path = app_info.get("path")
        if not path or not os.path.exists(path):
            QMessageBox.information(self, "Select Application",
                                    f"Select executable for {key}")
            path, _ = QFileDialog.getOpenFileName(
                self, f"Select {key} executable")
            if path:
                app_info["path"] = path
                self.config[key] = app_info
                self.save_config()
                if key not in [self.app_list.item(i).text() for i in range(self.app_list.count())]:
                    self.app_list.addItem(key)
        return app_info

    def launch_selected_app(self):
        """Launch app selected in the list."""
        item = self.app_list.currentItem()
        if not item:
            QMessageBox.warning(self, "No Selection", "Please select an application to launch.")
            return
        key = item.text()
        self.run_app(key)

    def run_app(self, key):
        """Run an application based on its settings."""
        app_info = self.get_app_info(key)
        path = app_info.get("path")
        if not path:
            return

        args = []

        # If file_input is enabled → open file picker
        if app_info.get("file_input"):
            file_path, _ = QFileDialog.getOpenFileName(self, f"Select file for {key}")
            if not file_path:
                return
            args.append(file_path)

        if app_info.get("cli"):
            # Run as CLI → capture output
            self.run_cli(path, args)
        else:
            # Run as UI app
            try:
                subprocess.Popen([path] + args)
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def run_cli(self, path, args):
        """Run a CLI application and capture output."""
        self.output_area.clear()
        self.output_area.append(f"Running {path} {' '.join(args)}\n")

        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.handle_finished)

        self.process.start(path, args)

    def handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode()
        self.output_area.append(data)

    def handle_stderr(self):
        data = self.process.readAllStandardError().data().decode()
        self.output_area.append(f"[ERROR] {data}")

    def handle_finished(self):
        self.output_area.append("\n--- Process Finished ---\n")
        self.process = None

    def add_application(self):
        """Add a new application from the UI."""
        exe_path, _ = QFileDialog.getOpenFileName(self, "Select Application Executable")
        if not exe_path:
            return

        # Default name = filename
        default_name = os.path.splitext(os.path.basename(exe_path))[0]
        name, ok = QInputDialog.getText(self, "Application Name", "Enter name:", text=default_name)
        if not ok or not name.strip():
            return
        name = name.strip()

        # Optional settings dialog
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Settings for {name}")
        layout = QFormLayout(dialog)
        cli_checkbox = QCheckBox("CLI Tool (capture output)")
        file_input_checkbox = QCheckBox("File Input (prompt for file)")
        layout.addRow(cli_checkbox)
        layout.addRow(file_input_checkbox)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec_() != QDialog.Accepted:
            return

        app_info = {
            "path": exe_path,
            "cli": cli_checkbox.isChecked(),
            "file_input": file_input_checkbox.isChecked()
        }
        self.config[name] = app_info
        self.save_config()

    def show_context_menu(self, position):
        """Show right-click menu for app list items."""
        item = self.app_list.itemAt(position)
        if item is None:
            return

        menu = QMenu()
        remove_action = menu.addAction("Remove Application")
        # You can add more actions here later, e.g. Edit, Settings, etc.

        action = menu.exec_(self.app_list.viewport().mapToGlobal(position))
        if action == remove_action:
            self.remove_app(item.text())

    def remove_app(self, name):
        """Remove an application from the config and update the list."""
        confirm = QMessageBox.question(
            self, "Confirm Removal",
            f"Are you sure you want to remove '{name}' from the list?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            if name in self.config:
                del self.config[name]
                self.save_config()  # This will refresh the list


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(resource_path("resources/icons/icon.ico")))
    win = WorkflowLauncher()
    win.show()
    sys.exit(app.exec_())
