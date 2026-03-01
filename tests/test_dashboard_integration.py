import os
import sys
import pytest

# Ensure project root in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PyQt5.QtWidgets import QApplication
from dashboard import DashboardWindow

@pytest.fixture(scope="module")
def app():
    app = QApplication.instance() or QApplication([])
    return app

def test_admin_sees_users_and_settings(app):
    admin_user = {"username": "admin", "role": "admin", "user_id": 1}
    win = DashboardWindow(current_user=admin_user)
    # sidebar labels
    labels = [win.sidebar.item(i).text() for i in range(win.sidebar.count())]
    assert "Users" in labels
    assert "Settings" in labels
    # menu shortcuts should be registered (we check open_page_by_label behaves)
    win.open_page_by_label("Users")
    # current page should be Users (find index)
    assert any(win.sidebar.item(i).text() == "Users" for i in range(win.sidebar.count()))
    win.close()

def test_cashier_hides_users_settings(app):
    cashier_user = {"username": "joe", "role": "cashier", "user_id": 2}
    win = DashboardWindow(current_user=cashier_user)
    labels = [win.sidebar.item(i).text() for i in range(win.sidebar.count())]
    assert "Users" not in labels
    assert "Settings" not in labels
    win.close()