#!/usr/bin/env python3
"""
dashboard.py — robust mapping of sidebar labels to QStackedWidget pages.

Notes:
- Includes a small import hint block so PyInstaller detects page modules
  that are dynamically imported at runtime.
- Improved _safe_import_page logs exceptions to console and dashboard_errors.log
  to aid debugging in packaged builds.
- Adds a simple __main__ test harness so you can run `python dashboard.py`
  to open the dashboard window directly and view tracebacks.
"""
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QStackedWidget, QMessageBox, QAction, QToolBar, QStyle, QShortcut
)
from PyQt5.QtGui import QFont, QKeySequence
from PyQt5.QtCore import Qt
import traceback
import sys
import os

PLACEHOLDER_TEXT = "Placeholder page. Implementation will be provided."
ERROR_LOG = os.path.join(os.getcwd(), "dashboard_errors.log")

# -------------------------
# Help PyInstaller detect dynamic imports:
# PyInstaller static analysis may skip modules only imported via strings at runtime.
# Import them here (in a try/except) so PyInstaller sees them and bundles them.
try:
    # Local application modules that Dashboard may import dynamically
    import orders, payments, reports, users, settings, customers
except Exception:
    # ignore errors here; actual imports will be attempted dynamically at runtime
    pass
# -------------------------


class PlaceholderPage(QWidget):
    def __init__(self, title: str, description: str = ""):
        super().__init__()
        layout = QVBoxLayout()
        lbl = QLabel(title)
        lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
        layout.addWidget(lbl)
        desc = QLabel(description or PLACEHOLDER_TEXT)
        desc.setWordWrap(True)
        layout.addWidget(desc)
        layout.addStretch(1)
        self.setLayout(layout)


class DashboardWindow(QMainWindow):
    def __init__(self, current_user: dict):
        super().__init__()
        self.current_user = current_user
        self.setWindowTitle(f"LMS — Dashboard ({self.current_user.get('username')})")
        self.setMinimumSize(1000, 620)
        # Map of label -> stack index (populated after building pages)
        self.label_to_index = {}
        self._build_ui()
        self._register_shortcuts()

    def _log_import_error(self, import_path: str, class_name: str, exc: Exception):
        """Log import exceptions for diagnostics (console + file)."""
        tb = traceback.format_exc()
        msg = f"Error importing {class_name} from {import_path}:\n{exc}\n{tb}\n"
        try:
            # write to console (useful if running exe from console)
            print(msg, file=sys.stderr)
            # append to a persistent file for packaged app debugging
            with open(ERROR_LOG, "a", encoding="utf-8") as f:
                f.write(msg)
        except Exception:
            pass

    def _safe_import_page(self, import_path: str, class_name: str, *args, **kwargs):
        """
        Try to import class_name from import_path module and instantiate it with args/kwargs.
        On any exception, return a PlaceholderPage describing the error (but do not raise).
        This function logs detailed tracebacks to dashboard_errors.log so packaged EXEs are diagnosable.
        """
        try:
            mod = __import__(import_path, fromlist=[class_name])
            cls = getattr(mod, class_name)
            return cls(*args, **kwargs)
        except Exception as e:
            # Log full traceback to file + stderr for debugging packaged app problems
            self._log_import_error(import_path, class_name, e)
            desc = f"{class_name} from {import_path} not available: {e}"
            return PlaceholderPage(class_name, desc)

    def _build_ui(self):
        central = QWidget()
        main_layout = QHBoxLayout(central)
        self.setCentralWidget(central)

        # Sidebar
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(220)
        self.sidebar.setFont(QFont("Segoe UI", 10))
        self.sidebar.currentRowChanged.connect(self.change_page)
        main_layout.addWidget(self.sidebar)

        # Stack
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack, stretch=1)

        # Build pages list in a single ordered pass
        role = (self.current_user.get("role") or "cashier").lower()

        # Each entry: (label, factory_callable) — factory returns a QWidget
        pages = [
            ("Customers", lambda: self._safe_import_page("customers", "CustomersWidget")),
            ("Orders",   lambda: self._safe_import_page("orders", "OrdersWindow", current_user=self.current_user)),
            ("Payments", lambda: self._safe_import_page("payments", "PaymentsWindow", current_user=self.current_user)),
            ("Reports",  lambda: self._safe_import_page("reports", "ReportsWindow", current_user=self.current_user)),
        ]

        # conditional admin pages
        if role in ("admin", "manager"):
            pages.append(("Users",    lambda: self._safe_import_page("users", "UsersWindow", current_user=self.current_user)))
            pages.append(("Settings", lambda: self._safe_import_page("settings", "SettingsWindow")))

        pages.append(("Logout", lambda: PlaceholderPage("Logout", "Use this to log out.")))

        # Populate sidebar and stack in the same loop to ensure alignment
        for idx, (label, factory) in enumerate(pages):
            # create list item
            item = QListWidgetItem(label)
            item.setTextAlignment(Qt.AlignCenter)
            self.sidebar.addItem(item)
            # create page widget (factory may return PlaceholderPage on error)
            try:
                widget = factory()
            except TypeError:
                # Fallback if factory signature mismatch — safe placeholder
                widget = PlaceholderPage(label)
            # Add to stack
            self.stack.addWidget(widget)
            # record mapping label -> index
            self.label_to_index[label] = idx

        # Select first page by default (Customers)
        self.sidebar.setCurrentRow(0)

        # Menubar & toolbar (same behavior as earlier)
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        logout_action = QAction("Logout", self)
        logout_action.setShortcut("Ctrl+L")
        logout_action.triggered.connect(self.handle_logout)
        file_menu.addAction(logout_action)

        manage_menu = menubar.addMenu("&Manage")
        if role in ("admin", "manager"):
            users_action = QAction("Users", self)
            users_action.setShortcut("Ctrl+U")
            users_action.triggered.connect(self.open_users_page)
            manage_menu.addAction(users_action)

            settings_action = QAction("Settings", self)
            settings_action.setShortcut("Ctrl+T")
            settings_action.triggered.connect(self.open_settings_page)
            manage_menu.addAction(settings_action)

        reports_action = QAction("Reports", self)
        reports_action.setShortcut("Ctrl+R")
        reports_action.triggered.connect(lambda: self.open_page_by_label("Reports"))
        menubar.addAction(reports_action)

        toolbar = QToolBar("Quick Actions")
        self.addToolBar(toolbar)

        tb_logout = QAction(self.style().standardIcon(QStyle.SP_DialogCloseButton), "Logout", self)
        tb_logout.setShortcut("Ctrl+L")
        tb_logout.triggered.connect(self.handle_logout)
        toolbar.addAction(tb_logout)

        if role in ("admin", "manager"):
            tb_users = QAction(self.style().standardIcon(QStyle.SP_DirHomeIcon), "Users", self)
            tb_users.setShortcut("Ctrl+U")
            tb_users.triggered.connect(self.open_users_page)
            toolbar.addAction(tb_users)

            tb_settings = QAction(self.style().standardIcon(QStyle.SP_FileDialogDetailedView), "Settings", self)
            tb_settings.setShortcut("Ctrl+T")
            tb_settings.triggered.connect(self.open_settings_page)
            toolbar.addAction(tb_settings)

    def _register_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.handle_logout)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=lambda: self.open_page_by_label("Reports"))
        role = (self.current_user.get("role") or "cashier").lower()
        if role in ("admin", "manager"):
            QShortcut(QKeySequence("Ctrl+U"), self, activated=self.open_users_page)
            QShortcut(QKeySequence("Ctrl+T"), self, activated=self.open_settings_page)

    def change_page(self, _index):
        # Use the current item label and the map to find the stack index
        item = self.sidebar.currentItem()
        if not item:
            return
        label = item.text()
        if label == "Logout":
            self.handle_logout()
            return
        idx = self.label_to_index.get(label)
        if idx is None:
            return
        if 0 <= idx < self.stack.count():
            self.stack.setCurrentIndex(idx)

    def open_page_by_label(self, label: str):
        # select sidebar row by label if present
        for i in range(self.sidebar.count()):
            if self.sidebar.item(i).text() == label:
                self.sidebar.setCurrentRow(i)
                return

    def open_users_page(self):
        self.open_page_by_label("Users")

    def open_settings_page(self):
        self.open_page_by_label("Settings")

    def handle_logout(self):
        confirm = QMessageBox.question(self, "Logout", "Are you sure you want to logout?", QMessageBox.Yes | QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        self.close()


# -------------------------
# Debug / developer harness
# -------------------------
if __name__ == "__main__":
    # Run a simple dashboard window for local debugging and to show import errors on the console.
    try:
        from PyQt5.QtWidgets import QApplication
        app = QApplication(sys.argv)
        # Use a default admin-like user for the debug harness
        user = {"username": "admin", "role": "admin", "user_id": 1}
        w = DashboardWindow(current_user=user)
        w.show()
        sys.exit(app.exec_())
    except Exception:
        # If creating the window fails, show traceback on console and save to log
        tb = traceback.format_exc()
        print("Failed to launch Dashboard (see dashboard_errors.log):\n", tb, file=sys.stderr)
        try:
            with open(ERROR_LOG, "a", encoding="utf-8") as f:
                f.write(tb)
        except Exception:
            pass
        raise