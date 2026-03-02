# Laundry Management System (LMS)

A cross-platform desktop application for managing laundry shop operations — customers, orders, payments, invoices, and reports. Built with Python 3.12 + PyQt5, data stored locally in SQLite.

## Features

- **Customer Management** — Register, search, and view customer history
- **Order Processing** — Create orders with multiple line items, quantities, and custom pricing
- **Discounts** — Apply percentage or fixed-amount discounts
- **Payment Tracking** — Record full/partial payments; real-time balance calculation
- **Invoice Generation** — PDF invoices with company logo and details (ReportLab)
- **Reporting** — Daily sales reports + CSV export
- **Role-Based Access** — Cashier, Manager, Admin with distinct UI privileges
- **User Management** — Create/modify staff accounts; secure password hashing
- **Backup & Restore** — One-click database backups with safety auto-backup before restore
- **Company Settings** — Configure business info displayed on invoices
- **Printing** — Windows native printing support (optional pywin32)

## Tech Stack

| Component | Technology |
|----------|------------|
| Language | Python 3.12 |
| GUI Framework | PyQt5 |
| Database | SQLite3 |
| PDF Generation | ReportLab |
| Windows Printing | pywin32 (optional) |
| Packaging | PyInstaller |
| Testing | pytest |

## Project Structure
├── auth.py # Application entry point / login
├── dashboard.py # Main shell with sidebar + stacked pages
├── database.py # DB connection, schema init, path resolution
├── models.py # Data-access layer (all CRUD operations)
├── orders.py # Orders UI
├── customers.py # Customers UI
├── payments.py # Payments UI
├── reports.py # Reports UI + CSV export
├── users.py # User management UI
├── settings.py # Company settings UI + config.json
├── invoice.py # PDF invoice generation (ReportLab)
├── print_utils.py # Windows printing helpers (optional)
├── backup.py # Backup/restore UI + CLI functions
├── tests/ # Unit and integration tests
│ ├── test_models.py
│ └── test_dashboard_integration.py
├── icons/ # Application icons
├── style.qss # Qt stylesheet
├── requirements.txt # Python dependencies
├── build_exe.ps1 # PowerShell build script
├── build_exe.bat # CMD build wrapper
└── config.json # Created on first save (company info)

text

## Getting Started

### Prerequisites

- Python 3.12+
- Windows (primary target)

### Installation (Development)

```bash
# Clone the repository
git clone https://github.com/yourusername/laundry-management-system.git
cd laundry-management-system

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Generate icons (optional)
python generate_icons.py

# Run the application
python auth.py
Default login: admin / admin123 (change immediately after first login)

Database
Location: %APPDATA%\LaundryLMS\lms.db (packaged) or ./lms.db (source)

First run: Schema auto-created + default admin seeded

Backups: Stored in backups/ directory with timestamps

User Roles
Role	Permissions
Cashier	Customers, Orders, Payments, Invoice printing
Manager	Cashier + Reports, Settings, Backup & Restore
Admin	Manager + User management, full system access
Packaging with PyInstaller
ONEDIR (testing)
bash
pyinstaller --clean --noupx --onedir --name LaundryLMS auth.py
cd dist\LaundryLMS
.\LaundryLMS.exe
ONEFILE (production)
bash
pyinstaller --clean --noupx --onefile \
  --add-data "icons;icons" \
  --add-data "style.qss;." \
  --hidden-import=reportlab.rl_config \
  --hidden-import=orders \
  --hidden-import=customers \
  --hidden-import=payments \
  --hidden-import=reports \
  --hidden-import=users \
  --hidden-import=settings \
  --name LaundryLMS auth.py
Configuration
Environment Variables
Variable	Purpose	Example
LMS_DB_PATH	Override DB path (development only)	C:\data\lms.db
config.json
Created automatically via Settings UI:

json
{
  "company_name": "Sunshine Laundry",
  "address": "123 Main Street, Cityville",
  "phone": "+1-555-0100",
  "email": "info@sunshineLaundry.com",
  "logo_path": "C:/LaundryLMS/logo.png"
}
Testing
bash
# Run all tests
pytest -q

# Run specific test file
pytest tests/test_models.py -v
Backup & Restore
Create a backup
bash
python -c "from backup import backup_database; print(backup_database())"
Restore from backup
bash
python -c "from backup import restore_database; restore_database('backups/lms_backup_2026-03-01_18-30.db')"
Common Issues
Placeholder pages in packaged EXE
Cause: PyInstaller missed page modules.

Fix: Add explicit --hidden-import flags or import hints in dashboard.py:

python
try:
    import orders, customers, payments, reports, users, settings
except ImportError as e:
    print(f"Import error: {e}")
Database not found
Cause: Incorrect path resolution in frozen executable.

Fix: Ensure database.get_db_path() returns %APPDATA%\LaundryLMS\lms.db for packaged builds.

 

Contributing
Fork the repository

Create a feature branch

Commit your changes

Push to the branch

Open a Pull Request

Contact
baffoekuuku9@gmail.com
