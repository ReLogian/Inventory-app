import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(sys.argv[0])))


class InventoryApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Inventorius")
        self.root.geometry("1150x700")

        # ---------------- DB ----------------
        self.conn = sqlite3.connect("inventory.db")
        self.cur = self.conn.cursor()
        self.create_tables()

        self.selected_product_id = None
        self.sort_state = {"col": None, "reverse": False}

        # ---------------- INPUTS ----------------
        top = ttk.Frame(root)
        top.pack(fill=tk.X, padx=10, pady=10)

        self.barcode = self._entry(top, "Barcode", 0)
        self.name = self._entry(top, "Name", 1)
        self.brand = self._entry(top, "Brand", 2)
        self.category = self._entry(top, "Category", 3)
        self.price = self._entry(top, "Price", 4)

        self.barcode.focus_set()

        # ---------------- BUTTONS ----------------
        btns = ttk.Frame(root)
        btns.pack(fill=tk.X, padx=10)

        ttk.Button(btns, text="Prideti", command=self.add_stock).pack(side=tk.LEFT, padx=5)
        ttk.Button(btns, text="Atimti", command=self.remove_stock).pack(side=tk.LEFT, padx=5)
        ttk.Button(btns, text="Redaguoti", command=self.edit_product).pack(side=tk.LEFT, padx=5)
        ttk.Button(btns, text="Ištrinti", command=self.delete_product).pack(side=tk.LEFT, padx=5)
        ttk.Button(btns, text="Paieška", command=self.search).pack(side=tk.LEFT, padx=5)
        ttk.Button(btns, text="Atnaujinti", command=self.load_inventory).pack(side=tk.LEFT, padx=5)

        # ---------------- TABLE + SCROLL ----------------
        table_frame = ttk.Frame(root)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical")

        self.cols = ("barcode", "name", "brand", "category", "price", "quantity")

        self.tree = ttk.Treeview(
            table_frame,
            columns=self.cols,
            show="headings",
            yscrollcommand=scrollbar.set
        )

        scrollbar.config(command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        for c in self.cols:
            self.tree.heading(
                c,
                text=c,
                command=lambda _c=c: self.sort_treeview(_c, False)
            )
            self.tree.column(c, width=150)

        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.root.bind("<Return>", lambda e: self.search())

        self.load_inventory()

    # ---------------- DB ----------------
    def create_tables(self):
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            barcode TEXT UNIQUE,
            name TEXT,
            brand TEXT,
            category TEXT,
            price REAL
        )
        """)

        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            product_id INTEGER PRIMARY KEY,
            quantity INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)

        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            barcode TEXT,
            quantity INTEGER,
            sold_price REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)

        self.conn.commit()

    # ---------------- HELPERS ----------------
    def _entry(self, parent, label, col):
        ttk.Label(parent, text=label).grid(row=0, column=col)
        e = ttk.Entry(parent, width=18)
        e.grid(row=1, column=col, padx=5)
        return e

    def clear_inputs(self):
        self.barcode.delete(0, tk.END)
        self.name.delete(0, tk.END)
        self.brand.delete(0, tk.END)
        self.category.delete(0, tk.END)
        self.price.delete(0, tk.END)
        self.barcode.focus_set()

    def get_price_value(self):
        value = self.price.get().strip().replace(",", ".")

        if value == "":
            return 0.0

        try:
            return float(value)
        except ValueError:
            messagebox.showerror("Klaida", "Netinkamas formatas")
            self.price.focus_set()
            return None

    # ---------------- SELECT ----------------
    def on_select(self, event=None):
        selected = self.tree.selection()
        if not selected:
            return

        values = self.tree.item(selected[0], "values")

        self.clear_inputs()

        self.barcode.insert(0, values[0])
        self.name.insert(0, values[1])
        self.brand.insert(0, values[2])
        self.category.insert(0, values[3])
        self.price.insert(0, values[4])

        self.cur.execute("SELECT id FROM products WHERE barcode = ?", (values[0],))
        res = self.cur.fetchone()
        self.selected_product_id = res[0] if res else None

    # ---------------- LOAD ----------------
    def load_inventory(self):
        self.tree.delete(*self.tree.get_children())

        self.cur.execute("""
        SELECT p.barcode, p.name, p.brand, p.category, p.price, i.quantity
        FROM products p
        LEFT JOIN inventory i ON p.id = i.product_id
        ORDER BY p.name
        """)

        for row in self.cur.fetchall():
            self.tree.insert("", tk.END, values=row)

    # ---------------- SORT ----------------
    def sort_treeview(self, col, reverse):
        data = [(self.tree.set(k, col), k) for k in self.tree.get_children()]

        if col in ("price", "quantity"):
            data.sort(key=lambda t: float(t[0]) if t[0] else 0, reverse=reverse)
        else:
            data.sort(key=lambda t: str(t[0]).lower(), reverse=reverse)

        for i, (_, k) in enumerate(data):
            self.tree.move(k, "", i)

        for c in self.cols:
            self.tree.heading(c, text=c, command=lambda _c=c: self.sort_treeview(_c, False))

        arrow = " ▲" if not reverse else " ▼"
        self.tree.heading(col, text=col + arrow,
                          command=lambda: self.sort_treeview(col, not reverse))

    # ---------------- ADD ----------------
    def add_stock(self):
        barcode = self.barcode.get().strip()
        if not barcode:
            return

        price = self.get_price_value()
        if price is None:
            return

        self.cur.execute("SELECT id FROM products WHERE barcode = ?", (barcode,))
        product = self.cur.fetchone()

        if not product:
            self.cur.execute("""
            INSERT INTO products (barcode, name, brand, category, price)
            VALUES (?, ?, ?, ?, ?)
            """, (barcode, self.name.get(), self.brand.get(), self.category.get(), price))
            product_id = self.cur.lastrowid
        else:
            product_id = product[0]

        self.cur.execute("""
        INSERT OR IGNORE INTO inventory (product_id, quantity)
        VALUES (?, 0)
        """, (product_id,))

        self.cur.execute("""
        UPDATE inventory
        SET quantity = quantity + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE product_id = ?
        """, (product_id,))

        self.conn.commit()
        self.load_inventory()
        self.clear_inputs()

    # ---------------- REMOVE ----------------
    def remove_stock(self):
        barcode = self.barcode.get().strip()
        if not barcode:
            return

        price = self.get_price_value()
        if price is None:
            return

        self.cur.execute("SELECT id FROM products WHERE barcode = ?", (barcode,))
        res = self.cur.fetchone()

        if not res:
            messagebox.showerror("Error", "Product not found")
            return

        product_id = res[0]

        self.cur.execute("""
        UPDATE inventory
        SET quantity = MAX(quantity - 1, 0),
            updated_at = CURRENT_TIMESTAMP
        WHERE product_id = ?
        """, (product_id,))

        self.cur.execute("""
        INSERT INTO sales (product_id, barcode, quantity, sold_price)
        VALUES (?, ?, ?, ?)
        """, (product_id, barcode, 1, price))

        self.conn.commit()
        self.load_inventory()
        self.clear_inputs()

    # ---------------- EDIT ----------------
    def edit_product(self):
        if not self.selected_product_id:
            messagebox.showerror("Error", "No product selected")
            return

        price = self.get_price_value()
        if price is None:
            return

        self.cur.execute("""
        UPDATE products
        SET barcode = ?, name = ?, brand = ?, category = ?, price = ?
        WHERE id = ?
        """, (
            self.barcode.get().strip(),
            self.name.get().strip(),
            self.brand.get().strip(),
            self.category.get().strip(),
            price,
            self.selected_product_id
        ))

        self.conn.commit()
        self.load_inventory()
        self.clear_inputs()
        self.selected_product_id = None

    # ---------------- DELETE ----------------
    def delete_product(self):
        if not self.selected_product_id:
            messagebox.showerror("Error", "No product selected")
            return

        if not messagebox.askyesno("Confirm", "Delete this product?"):
            return

        self.cur.execute("DELETE FROM inventory WHERE product_id = ?", (self.selected_product_id,))
        self.cur.execute("DELETE FROM sales WHERE product_id = ?", (self.selected_product_id,))
        self.cur.execute("DELETE FROM products WHERE id = ?", (self.selected_product_id,))

        self.conn.commit()
        self.selected_product_id = None
        self.load_inventory()
        self.clear_inputs()

    # ---------------- SEARCH ----------------
    def search(self):
        query = self.barcode.get().strip()

        self.tree.delete(*self.tree.get_children())

        if not query:
            self.load_inventory()
            return

        like = f"%{query}%"

        self.cur.execute("""
        SELECT p.barcode, p.name, p.brand, p.category, p.price, i.quantity
        FROM products p
        LEFT JOIN inventory i ON p.id = i.product_id
        WHERE
            p.barcode LIKE ?
            OR p.name LIKE ?
            OR p.brand LIKE ?
            OR p.category LIKE ?
        ORDER BY p.name
        """, (like, like, like, like))

        for row in self.cur.fetchall():
            self.tree.insert("", tk.END, values=row)


if __name__ == "__main__":
    root = tk.Tk()
    app = InventoryApp(root)
    root.mainloop()