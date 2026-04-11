"""First-run setup wizard for API credentials configuration."""

import logging
from PyQt6 import QtWidgets, QtCore
from mpcamera.config import get_settings

logger = logging.getLogger(__name__)


class SetupWizardDialog(QtWidgets.QDialog):
    """Wizard dialog for configuring API credentials on first run."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SoilSight - Initial Setup")
        self.setModal(True)
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self.cfg = None
        self._init_ui()

    def _init_ui(self):
        """Build the wizard UI with tabs for Roboflow and Directus."""
        layout = QtWidgets.QVBoxLayout()

        # Title
        title = QtWidgets.QLabel("Welcome to SoilSight!")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # Instructions
        instructions = QtWidgets.QLabel(
            "Please configure your API credentials below. You can also configure these later in Settings."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Tab widget
        self.tabs = QtWidgets.QTabWidget()

        # Roboflow tab
        self.tabs.addTab(self._create_roboflow_tab(), "Roboflow")

        # Directus tab
        self.tabs.addTab(self._create_directus_tab(), "Directus")

        layout.addWidget(self.tabs)

        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()

        skip_btn = QtWidgets.QPushButton("Skip for Now")
        skip_btn.clicked.connect(self.reject)
        btn_layout.addWidget(skip_btn)

        save_btn = QtWidgets.QPushButton("Save & Continue")
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def _create_roboflow_tab(self):
        """Create Roboflow configuration tab."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()

        # API Key
        layout.addWidget(QtWidgets.QLabel("API Key:"))
        self.rf_api_key = QtWidgets.QLineEdit()
        self.rf_api_key.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        layout.addWidget(self.rf_api_key)

        # API URL
        layout.addWidget(QtWidgets.QLabel("API URL:"))
        self.rf_api_url = QtWidgets.QLineEdit()
        self.rf_api_url.setPlaceholderText("e.g., http://localhost:9001 or https://api.roboflow.com")
        layout.addWidget(self.rf_api_url)

        # Workspace
        layout.addWidget(QtWidgets.QLabel("Workspace:"))
        self.rf_workspace = QtWidgets.QLineEdit()
        layout.addWidget(self.rf_workspace)

        # Workflow
        layout.addWidget(QtWidgets.QLabel("Workflow (Model ID):"))
        self.rf_workflow = QtWidgets.QLineEdit()
        layout.addWidget(self.rf_workflow)

        layout.addStretch()

        help_text = QtWidgets.QLabel(
            "ℹ️ Get these credentials from your Roboflow account.\n"
            "Leave blank to skip (you can configure later in Settings)."
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(help_text)

        widget.setLayout(layout)
        return widget

    def _create_directus_tab(self):
        """Create Directus configuration tab."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()

        # API URL
        layout.addWidget(QtWidgets.QLabel("API URL:"))
        self.du_api_url = QtWidgets.QLineEdit()
        self.du_api_url.setPlaceholderText("e.g., https://directus.example.com")
        layout.addWidget(self.du_api_url)

        # Bearer Token
        layout.addWidget(QtWidgets.QLabel("Bearer Token:"))
        self.du_bearer = QtWidgets.QLineEdit()
        self.du_bearer.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        layout.addWidget(self.du_bearer)

        # Timeout
        layout.addWidget(QtWidgets.QLabel("Timeout (seconds):"))
        self.du_timeout = QtWidgets.QSpinBox()
        self.du_timeout.setMinimum(5)
        self.du_timeout.setMaximum(300)
        self.du_timeout.setValue(30)
        layout.addWidget(self.du_timeout)

        layout.addStretch()

        help_text = QtWidgets.QLabel(
            "ℹ️ Directus is used to fetch soil sample data.\n"
            "Leave blank to skip (you can configure later in Settings)."
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(help_text)

        widget.setLayout(layout)
        return widget

    def _on_save(self):
        """Save the configuration."""
        try:
            self.cfg = get_settings()
        except Exception as e:
            logger.error(f"Failed to load settings: {e}")
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                f"Failed to load settings: {e}"
            )
            return

        # Save Roboflow if provided
        if self.rf_api_key.text().strip():
            self.cfg["services"]["roboflow"]["api_key"] = self.rf_api_key.text().strip()
        if self.rf_api_url.text().strip():
            self.cfg["services"]["roboflow"]["api_url"] = self.rf_api_url.text().strip()
        if self.rf_workspace.text().strip():
            self.cfg["services"]["roboflow"]["workspace"] = self.rf_workspace.text().strip()
        if self.rf_workflow.text().strip():
            self.cfg["services"]["roboflow"]["workflow"] = self.rf_workflow.text().strip()

        # Save Directus if provided
        if self.du_api_url.text().strip():
            self.cfg["services"]["directus"]["api_url"] = self.du_api_url.text().strip()
        if self.du_bearer.text().strip():
            self.cfg["services"]["directus"]["bearer_token"] = self.du_bearer.text().strip()
        self.cfg["services"]["directus"]["timeout_seconds"] = self.du_timeout.value()

        try:
            self.cfg.save()
            logger.info("Setup wizard configuration saved successfully")
            QtWidgets.QMessageBox.information(
                self,
                "Success",
                "Configuration saved successfully!"
            )
            self.accept()
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                f"Failed to save configuration: {e}"
            )

    def load_current_values(self):
        """Load current values from settings for editing."""
        try:
            cfg = get_settings()
            self.rf_api_key.setText(cfg.get("services", {}).get("roboflow", {}).get("api_key", ""))
            self.rf_api_url.setText(cfg.get("services", {}).get("roboflow", {}).get("api_url", ""))
            self.rf_workspace.setText(cfg.get("services", {}).get("roboflow", {}).get("workspace", ""))
            self.rf_workflow.setText(cfg.get("services", {}).get("roboflow", {}).get("workflow", ""))

            self.du_api_url.setText(cfg.get("services", {}).get("directus", {}).get("api_url", ""))
            self.du_bearer.setText(cfg.get("services", {}).get("directus", {}).get("bearer_token", ""))
            self.du_timeout.setValue(cfg.get("services", {}).get("directus", {}).get("timeout_seconds", 30))
        except Exception as e:
            logger.debug(f"Could not load current values: {e}")

    @staticmethod
    def should_show_wizard():
        """Determine if the wizard should be shown on startup."""
        try:
            cfg = get_settings()
            # Show wizard if either Roboflow API key or Directus URL is missing
            has_rf_key = cfg.get("services", {}).get("roboflow", {}).get("api_key", "").strip()
            has_du_url = cfg.get("services", {}).get("directus", {}).get("api_url", "").strip()

            # Show if either is missing (not just both)
            return not (has_rf_key and has_du_url)
        except Exception:
            # On error, don't force wizard
            return False
