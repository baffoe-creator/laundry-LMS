import os
import sys
import tempfile
import shutil
import pytest

# Ensure project root is on sys.path so 'database' and 'models' can be imported
# This file lives in tests/, so project root is parent directory
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def make_temp_db_path():
    tmpdir = tempfile.mkdtemp(prefix="lms_test_")
    dbpath = os.path.join(tmpdir, "lms_test.db")
    return dbpath, tmpdir

@pytest.fixture
def temp_db():
    dbpath, tmpdir = make_temp_db_path()
    # Initialize DB at this path
    import database
    # initialize the db at the given path; use force=True to ensure a clean file
    database.init_db(db_path=dbpath, force=True)
    # override env var so further imports use the temp DB
    os.environ["LMS_DB_PATH"] = dbpath
    # reload database module so connect_db picks up LMS_DB_PATH
    import importlib
    importlib.reload(database)
    # seed admin in the temp DB
    created, msg = database.seed_admin()
    yield dbpath
    # Teardown
    try:
        shutil.rmtree(tmpdir)
    except Exception:
        pass

def test_create_customer_and_order_and_payment(temp_db):
    # ensure models picks up LMS_DB_PATH; import after fixture set env var
    import importlib
    import database
    import models
    importlib.reload(models)

    # Create a customer
    cid = models.create_customer("Unit Tester", "0700123456")
    assert isinstance(cid, int) and cid > 0

    # Get admin user id
    admin = database.get_user_by_username("admin")
    assert admin is not None

    # Create order with 10% discount
    oid = models.create_order(customer_id=cid, created_by=admin["user_id"], discount=10.0, discount_type="percent")
    assert isinstance(oid, int) and oid > 0

    # Add two items
    item1 = models.add_order_item(oid, "Shirt", "Colored", 3, 2.5)  # subtotal 7.5
    item2 = models.add_order_item(oid, "Trousers", "White", 2, 3.75)  # subtotal 7.5
    assert item1 and item2

    # Compute totals explicitly
    totals = models.compute_order_totals(oid)
    # subtotal 15.00, discount 10% -> 1.5, total 13.5
    assert totals["subtotal"] == pytest.approx(15.00, rel=1e-6)
    assert totals["discount_amount"] == pytest.approx(1.50, rel=1e-6)
    assert totals["total_amount"] == pytest.approx(13.50, rel=1e-6)
    assert totals["paid_amount"] == pytest.approx(0.00, rel=1e-6)
    assert totals["balance"] == pytest.approx(13.50, rel=1e-6)

    # Record a partial payment
    pid = models.record_payment(oid, 5.0, notes="Test partial")
    assert isinstance(pid, int) and pid > 0

    # Check paid amount and balance updated
    snap = models.get_order_with_items(oid)
    assert snap["order"]["paid_amount"] == pytest.approx(5.0, rel=1e-6)
    assert snap["order"]["balance"] == pytest.approx(8.5, rel=1e-6)

    # Record full remaining payment
    pid2 = models.record_payment(oid, 8.50, notes="Remaining")
    snap2 = models.get_order_with_items(oid)
    assert snap2["order"]["paid_amount"] == pytest.approx(13.5, rel=1e-6)
    assert snap2["order"]["balance"] == pytest.approx(0.0, rel=1e-6)

    # Daily report for today's date must include this order
    date_str = snap2["order"]["order_date"].split(" ")[0]
    rep = models.daily_report(date_str)
    assert rep["total_orders"] >= 1
    assert rep["total_sales"] >= 0.0