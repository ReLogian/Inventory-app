import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from inventorymgmt import (  # noqa: E402
    CATEGORY_FILTER_ALL,
    create_schema,
    fetch_filtered_inventory_rows,
    fetch_inventory_rows,
    fetch_sales_summary_rows,
)


class InventoryCoreTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        create_schema(self.conn)
        self.cur = self.conn.cursor()
        self._insert_product("111", "iPhone 15 stiklas", "Apple", "Apsauginis stiklas", 14.0, 3)
        self._insert_product("222", "Samsung A55 stiklas", "Samsung", "Apsauginis stiklas", 12.0, 4)
        self._insert_product("333", "Apple USB-C laidas", "Apple", "Laidas", 8.0, 2)

        self.cur.execute("""
        INSERT INTO sales (product_id, barcode, quantity, sold_price, created_at)
        VALUES (1, '111', 2, 14.0, '2026-07-15 10:00:00')
        """)
        self.cur.execute("""
        INSERT INTO sales (product_id, barcode, quantity, sold_price, created_at)
        VALUES (3, '333', 1, 8.0, '2026-07-14 10:00:00')
        """)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def _insert_product(self, barcode, name, brand, category, price, quantity):
        self.cur.execute("""
        INSERT INTO products (barcode, name, brand, category, price)
        VALUES (?, ?, ?, ?, ?)
        """, (barcode, name, brand, category, price))
        product_id = self.cur.lastrowid
        self.cur.execute("""
        INSERT INTO inventory (product_id, quantity)
        VALUES (?, ?)
        """, (product_id, quantity))

    def test_inventory_rows_include_quantity(self):
        rows = fetch_inventory_rows(self.cur)
        self.assertEqual(len(rows), 3)
        self.assertIn(("111", "iPhone 15 stiklas", "Apple", "Apsauginis stiklas", 14.0, 3), rows)

    def test_search_combines_text_and_category(self):
        rows = fetch_filtered_inventory_rows(self.cur, "Apple", "Apsauginis stiklas")
        self.assertEqual(rows, [("111", "iPhone 15 stiklas", "Apple", "Apsauginis stiklas", 14.0, 3)])

    def test_category_filter_works_without_text_query(self):
        rows = fetch_filtered_inventory_rows(self.cur, "", "Apsauginis stiklas")
        self.assertEqual([row[0] for row in rows], ["222", "111"])

    def test_all_category_text_search(self):
        rows = fetch_filtered_inventory_rows(self.cur, "Apple", CATEGORY_FILTER_ALL)
        self.assertEqual([row[0] for row in rows], ["333", "111"])

    def test_sales_summary_uses_date_window(self):
        rows = fetch_sales_summary_rows(self.cur, "2026-07-15 00:00:00", "2026-07-16 00:00:00")
        self.assertEqual(rows, [("iPhone 15 stiklas", "111", 2, 28.0)])


if __name__ == "__main__":
    unittest.main()
