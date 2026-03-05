#!/usr/bin/env python3
"""
dashboard.py — robust mapping of sidebar labels to QStackedWidget pages.

Updated with:
- Header bar with logo and user info
- Sidebar object name for QSS styling
- Pointer cursors on buttons
- Smarter scrollable layout - only scroll when needed
- Increased minimum size for better visibility
- Fixed toolbar icons - distinct icons for Settings and Pricing
"""

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QStackedWidget, QMessageBox, QAction, QToolBar, QStyle, QShortcut,
    QScrollArea, QSizePolicy
)
from PyQt5.QtGui import QFont, QKeySequence, QPixmap
from PyQt5.QtCore import Qt
import traceback
import sys
import os

PLACEHOLDER_TEXT = "Placeholder page. Implementation will be provided."
ERROR_LOG = os.path.join(os.getcwd(), "dashboard_errors.log")

# -------------------------
# Help PyInstaller detect dynamic imports
try:
    import orders, payments, reports, users, settings, customers, pricing_admin
except Exception:
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


def _make_scrollable_if_needed(widget: QWidget) -> QWidget:
    """
    Only wrap in scroll area if the widget's natural size is likely to exceed viewport.
    Returns either the original widget or wrapped in scroll area.
    """
    if hasattr(widget, 'findChildren'):
        children = widget.findChildren(QWidget)
        if len(children) > 15:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll.setWidget(widget)
            return scroll
    return widget


class DashboardWindow(QMainWindow):
    def __init__(self, current_user: dict):
        super().__init__()
        self.current_user = current_user
        self.setWindowTitle(f"LMS — Dashboard ({self.current_user.get('username')})")
        self.setMinimumSize(1000, 620)
        self.label_to_index = {}
        self._build_ui()
        self._register_shortcuts()

    def _log_import_error(self, import_path: str, class_name: str, exc: Exception):
        tb = traceback.format_exc()
        msg = f"Error importing {class_name} from {import_path}:\n{exc}\n{tb}\n"
        try:
            print(msg, file=sys.stderr)
            with open(ERROR_LOG, "a", encoding="utf-8") as f:
                f.write(msg)
        except Exception:
            pass

    def _safe_import_page(self, import_path: str, class_name: str, *args, **kwargs):
        try:
            mod = __import__(import_path, fromlist=[class_name])
            cls = getattr(mod, class_name)
            return cls(*args, **kwargs)
        except Exception as e:
            self._log_import_error(import_path, class_name, e)
            desc = f"{class_name} from {import_path} not available: {e}"
            return PlaceholderPage(class_name, desc)

    def _build_ui(self):
        central = QWidget()
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.setCentralWidget(central)

        # Header Bar
        header = QWidget()
        header.setFixedHeight(60)
        header.setStyleSheet("background-color: #FFFFFF; border-bottom: 1px solid #DDE2E8;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 8, 16, 8)

        logo = QLabel("🧺 Laundry MS")
        logo.setObjectName("headerLogo")
        logo.setFont(QFont("Segoe UI", 14, QFont.Bold))
        header_layout.addWidget(logo)

        header_layout.addStretch()

        role = self.current_user.get("role", "cashier").capitalize()
        username = self.current_user.get("username", "User")
        user_info = QLabel(f"{username} ({role})")
        user_info.setObjectName("headerUser")
        user_info.setFont(QFont("Segoe UI", 10))
        header_layout.addWidget(user_info)

        main_layout.addWidget(header)

        # Main Content Area
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(220)
        self.sidebar.setFont(QFont("Segoe UI", 10))
        self.sidebar.currentRowChanged.connect(self.change_page)
        content_layout.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content_layout.addWidget(self.stack, stretch=1)

        main_layout.addWidget(content, stretch=1)

        # Build pages list
        role = (self.current_user.get("role") or "cashier").lower()

        pages = [
            ("Customers", lambda: self._safe_import_page("customers", "CustomersWidget")),
            ("Orders",   lambda: self._safe_import_page("orders", "OrdersWindow", current_user=self.current_user)),
            ("Payments", lambda: self._safe_import_page("payments", "PaymentsWindow", current_user=self.current_user)),
            ("Reports",  lambda: self._safe_import_page("reports", "ReportsWindow", current_user=self.current_user)),
        ]

        if role in ("admin", "manager"):
            pages.append(("Users",    lambda: self._safe_import_page("users", "UsersWindow", current_user=self.current_user)))
            pages.append(("Settings", lambda: self._safe_import_page("settings", "SettingsWindow")))
            pages.append(("Pricing",  lambda: self._safe_import_page("pricing_admin", "PricingAdminWidget", current_user=self.current_user)))

        pages.append(("Logout", lambda: PlaceholderPage("Logout", "Use this to log out.")))

        # Populate sidebar and stack
        for idx, (label, factory) in enumerate(pages):
            item = QListWidgetItem(label)
            item.setTextAlignment(Qt.AlignCenter)
            self.sidebar.addItem(item)
            
            try:
                widget = factory()
            except TypeError:
                widget = PlaceholderPage(label)
            
            page_widget = _make_scrollable_if_needed(widget)
            self.stack.addWidget(page_widget)
            self.label_to_index[label] = idx

        self.sidebar.setCurrentRow(0)

        # Menubar
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
            
            pricing_action = QAction("Pricing", self)
            pricing_action.setShortcut("Ctrl+P")
            pricing_action.triggered.connect(self.open_pricing_page)
            manage_menu.addAction(pricing_action)

        reports_action = QAction("Reports", self)
        reports_action.setShortcut("Ctrl+R")
        reports_action.triggered.connect(lambda: self.open_page_by_label("Reports"))
        menubar.addAction(reports_action)

        # Toolbar - Fixed icons: Settings and Pricing now have distinct icons
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

            # Settings keeps the detailed view icon
            tb_settings = QAction(self.style().standardIcon(QStyle.SP_FileDialogDetailedView), "Settings", self)
            tb_settings.setShortcut("Ctrl+T")
            tb_settings.triggered.connect(self.open_settings_page)
            toolbar.addAction(tb_settings)
            
            # Pricing gets a different icon for distinction
            tb_pricing = QAction(self.style().standardIcon(QStyle.SP_FileDialogListView), "Pricing", self)
            tb_pricing.setShortcut("Ctrl+P")
            tb_pricing.triggered.connect(self.open_pricing_page)
            toolbar.addAction(tb_pricing)

    def _register_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.handle_logout)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=lambda: self.open_page_by_label("Reports"))
        role = (self.current_user.get("role") or "cashier").lower()
        if role in ("admin", "manager"):
            QShortcut(QKeySequence("Ctrl+U"), self, activated=self.open_users_page)
            QShortcut(QKeySequence("Ctrl+T"), self, activated=self.open_settings_page)
            QShortcut(QKeySequence("Ctrl+P"), self, activated=self.open_pricing_page)

    def change_page(self, _index):
        item = self.sidebar.currentItem()
        if not item:
            return
        label = item.text()
        if label == "Logout":
            self.handle_logout()
            return
        idx = self.label_to_index.get(label)
        if idx is not None and 0 <= idx < self.stack.count():
            self.stack.setCurrentIndex(idx)

    def open_page_by_label(self, label: str):
        for i in range(self.sidebar.count()):
            if self.sidebar.item(i).text() == label:
                self.sidebar.setCurrentRow(i)
                return

    def open_users_page(self):
        self.open_page_by_label("Users")

    def open_settings_page(self):
        self.open_page_by_label("Settings")
        
    def open_pricing_page(self):
        self.open_page_by_label("Pricing")

    def handle_logout(self):
        confirm = QMessageBox.question(self, "Logout", "Are you sure you want to logout?", QMessageBox.Yes | QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        self.close()


if __name__ == "__main__":
    try:
        from PyQt5.QtWidgets import QApplication
        app = QApplication(sys.argv)
        user = {"username": "admin", "role": "admin", "user_id": 1}
        w = DashboardWindow(current_user=user)
        w.show()
        sys.exit(app.exec_())
    except Exception:
        tb = traceback.format_exc()
        print("Failed to launch Dashboard (see dashboard_errors.log):\n", tb, file=sys.stderr)
        try:
            with open(ERROR_LOG, "a", encoding="utf-8") as f:
                f.write(tb)
        except Exception:
            pass
        raise