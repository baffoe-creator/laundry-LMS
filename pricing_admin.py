#!/usr/bin/env python3
"""
pricing_admin.py

Price Management UI for Admin/Manager roles.

This widget allows viewing and editing the price catalogue.
- Cashiers see read-only view
- Admins/Managers can edit prices and save changes
- Changes take effect immediately in OrdersWindow

Integrated into dashboard.py with role-based visibility.
"""

from typing import Optional, Dict, Any, List
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QMessageBox, QHeaderView, QGroupBox
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt

import models
import database


class PricingAdminWidget(QWidget):
    """
    Price catalogue management widget.
    Editable for admin/manager, read-only for cashier.
    """
    
    def __init__(self, current_user: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.current_user = current_user or {}
        self.role = self.current_user.get('role', 'cashier').lower()
        self.is_editable = self.role in ('admin', 'manager')
        self.price_data: List[Dict[str, Any]] = []
        self.modified_rows: set = set()
        
        self.setWindowTitle("Price Catalogue Management")
        self._build_ui()
        self.load_prices()
    
    def _build_ui(self):
        """Build the UI layout."""
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Price Catalogue")
        title_font = QFont("Segoe UI", 14, QFont.Bold)
        title.setFont(title_font)
        layout.addWidget(title)
        
        # Role indicator
        role_text = f"Mode: {'Editable' if self.is_editable else 'Read-Only'}"
        role_label = QLabel(role_text)
        role_label.setFont(QFont("Segoe UI", 10))
        role_label.setStyleSheet("color: gray;")
        layout.addWidget(role_label)
        
        # Price table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            "Item Name", "Coloured (GH₵)", "White (GH₵)", "Pressing (GH₵)"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        if self.is_editable:
            self.table.itemChanged.connect(self.on_item_changed)
        
        layout.addWidget(self.table)
        
        # Button panel
        button_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.load_prices)
        button_layout.addWidget(self.refresh_btn)
        
        if self.is_editable:
            self.save_btn = QPushButton("Save Changes")
            self.save_btn.clicked.connect(self.save_changes)
            self.save_btn.setEnabled(False)
            button_layout.addWidget(self.save_btn)
            
            self.reset_btn = QPushButton("Reset")
            self.reset_btn.clicked.connect(self.load_prices)
            button_layout.addWidget(self.reset_btn)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # Instructions
        if self.is_editable:
            instructions = QLabel(
                "Double-click cells to edit. Changed rows are highlighted. "
                "Click 'Save Changes' to persist modifications."
            )
            instructions.setWordWrap(True)
            instructions.setStyleSheet("color: blue;")
            layout.addWidget(instructions)
        else:
            instructions = QLabel("Viewing in read-only mode (cashier). Contact manager to modify prices.")
            instructions.setWordWrap(True)
            instructions.setStyleSheet("color: gray;")
            layout.addWidget(instructions)
        
        self.setLayout(layout)
    
    def load_prices(self):
        """Load price data from database."""
        try:
            self.price_data = models.get_all_prices()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load prices: {e}")
            self.price_data = []
        
        # Disconnect itemChanged signal while populating
        if self.is_editable:
            self.table.itemChanged.disconnect(self.on_item_changed)
        
        self.table.setRowCount(len(self.price_data))
        
        for i, item in enumerate(self.price_data):
            # Item name (read-only)
            name_item = QTableWidgetItem(item['item_name'])
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            if not self.is_editable:
                name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 0, name_item)
            
            # Price columns
            self._set_price_cell(i, 1, item['price_coloured'])
            self._set_price_cell(i, 2, item['price_white'])
            self._set_price_cell(i, 3, item['price_pressing'])
        
        self.modified_rows.clear()
        if self.is_editable:
            self.save_btn.setEnabled(False)
            self.table.itemChanged.connect(self.on_item_changed)
    
    def _set_price_cell(self, row: int, col: int, value: Optional[float]):
        """Set a price cell with proper formatting."""
        item = QTableWidgetItem()
        if value is None:
            item.setText("")
            item.setForeground(QColor(150, 150, 150))
            item.setToolTip("Not available")
        else:
            item.setText(f"{value:.2f}")
        
        if not self.is_editable:
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        
        self.table.setItem(row, col, item)
    
    def on_item_changed(self, item: QTableWidgetItem):
        """Handle cell edits - highlight modified rows."""
        row = item.row()
        self.modified_rows.add(row)
        
        # Highlight the entire row
        for col in range(self.table.columnCount()):
            cell = self.table.item(row, col)
            if cell:
                cell.setBackground(QColor(255, 255, 200))  # Light yellow
        
        self.save_btn.setEnabled(True)
    
    def save_changes(self):
        """Save modified prices to database."""
        if not self.modified_rows:
            return
        
        success_count = 0
        error_count = 0
        
        for row in sorted(self.modified_rows):
            item_name = self.table.item(row, 0).text()
            
            # Parse price values (empty = None)
            try:
                coloured_text = self.table.item(row, 1).text().strip()
                price_coloured = float(coloured_text) if coloured_text else None
            except ValueError:
                price_coloured = None
            
            try:
                white_text = self.table.item(row, 2).text().strip()
                price_white = float(white_text) if white_text else None
            except ValueError:
                price_white = None
            
            try:
                pressing_text = self.table.item(row, 3).text().strip()
                price_pressing = float(pressing_text) if pressing_text else None
            except ValueError:
                price_pressing = None
            
            # Update database
            try:
                if models.update_item_price(item_name, price_coloured, price_white, price_pressing):
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                error_count += 1
                print(f"Error updating {item_name}: {e}")
        
        if error_count == 0:
            QMessageBox.information(
                self, "Success", 
                f"Successfully updated {success_count} item(s)."
            )
            # Clear highlighting
            for row in self.modified_rows:
                for col in range(self.table.columnCount()):
                    cell = self.table.item(row, col)
                    if cell:
                        cell.setBackground(QColor(255, 255, 255))  # White
        else:
            QMessageBox.warning(
                self, "Partial Success",
                f"Updated {success_count} item(s). Failed to update {error_count} item(s)."
            )
        
        self.modified_rows.clear()
        self.save_btn.setEnabled(False)
        
        # Reload to ensure fresh data
        self.load_prices()


if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    
    # Test as admin
    user = {"username": "admin", "role": "admin", "user_id": 1}
    w = PricingAdminWidget(current_user=user)
    w.show()
    
    sys.exit(app.exec_())