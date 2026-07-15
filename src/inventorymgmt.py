import csv
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox, filedialog
import sqlite3
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(sys.argv[0])))


class InventoryApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Inventorius")
        self.root.geometry("1150x700")
        self.root.minsize(950, 600)

        # ---------------- DB ----------------
        self.conn = sqlite3.connect("inventory.db")
        self.cur = self.conn.cursor()
        self.create_tables()

        self.selected_product_id = None
        self.sort_state = {"col": None, "reverse": False}

        style = ttk.Style()
        style.configure("Treeview", rowheight=26)

        # ---------------- INPUTS ----------------
        top = ttk.LabelFrame(root, text="Prekės informacija", padding=10)
        top.pack(fill=tk.X, padx=12, pady=(12, 6))

        self.barcode = self._entry(top, "Barcode", 0)
        self.name = self._entry(top, "Name", 1)
        self.brand = self._entry(top, "Brand", 2)
        self.category = self._entry(top, "Category", 3)
        self.price = self._entry(top, "Price", 4)

        for col in range(5):
            top.columnconfigure(col, weight=1)

        self.barcode.focus_set()

        # ---------------- BUTTONS ----------------
        btns = ttk.Frame(root)
        btns.pack(fill=tk.X, padx=12, pady=6)

        ttk.Button(btns, text="Pridėti", command=self.add_stock).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btns, text="Atimti", command=self.remove_stock).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Redaguoti", command=self.edit_product).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Ištrinti", command=self.delete_product).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Atnaujinti", command=self.load_inventory).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Eksportuoti CSV", command=self.export_csv).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(btns, text="Importuoti CSV", command=self.import_csv).pack(side=tk.RIGHT, padx=6)
        ttk.Button(btns, text="Mėnesio suvestinė", command=self.show_monthly_summary).pack(side=tk.RIGHT, padx=6)

        # ---------------- SEARCH ----------------
        search_frame = ttk.LabelFrame(root, text="Paieška", padding=10)
        search_frame.pack(fill=tk.X, padx=12, pady=6)

        ttk.Label(search_frame, text="Ieškoti").pack(side=tk.LEFT)
        self.search_query = ttk.Entry(search_frame)
        self.search_query.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        ttk.Button(search_frame, text="Paieška", command=self.search).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(search_frame, text="Valyti", command=self.clear_search).pack(side=tk.LEFT)

        # ---------------- TABLE + SCROLL ----------------
        table_frame = ttk.Frame(root)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(6, 12))

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
            width = 110 if c in ("price", "quantity") else 170
            self.tree.column(c, width=width, minwidth=90)

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
        e.grid(row=1, column=col, padx=5, pady=(4, 0), sticky="ew")
        return e

    def clear_inputs(self):
        self.barcode.delete(0, tk.END)
        self.name.delete(0, tk.END)
        self.brand.delete(0, tk.END)
        self.category.delete(0, tk.END)
        self.price.delete(0, tk.END)
        self.barcode.focus_set()

    def get_price_value(self, default=0.0):
        value = self.price.get().strip().replace(",", ".")

        if value == "":
            return default

        try:
            price = float(value)
        except ValueError:
            messagebox.showerror("Klaida", "Kaina turi būti skaičius, pvz. 12.50")
            self.price.focus_set()
            return None

        if price < 0:
            messagebox.showerror("Klaida", "Kaina negali būti neigiama")
            self.price.focus_set()
            return None

        return price

    def require_barcode(self):
        barcode = self.barcode.get().strip()
        if not barcode:
            messagebox.showerror("Klaida", "Įveskite prekės barkodą")
            self.barcode.focus_set()
            return None
        return barcode

    def get_existing_quantity(self, product_id):
        self.cur.execute("SELECT quantity FROM inventory WHERE product_id = ?", (product_id,))
        row = self.cur.fetchone()
        return row[0] if row else 0

    def format_price(self, value):
        return f"{float(value or 0):.2f}"

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
        self.search_query.delete(0, tk.END)
        self.tree.delete(*self.tree.get_children())

        self.cur.execute("""
        SELECT p.barcode, p.name, p.brand, p.category, p.price, i.quantity
        FROM products p
        LEFT JOIN inventory i ON p.id = i.product_id
        ORDER BY p.name
        """)

        for row in self.cur.fetchall():
            self.tree.insert("", tk.END, values=self.format_inventory_row(row))

    def format_inventory_row(self, row):
        barcode, name, brand, category, price, quantity = row
        return (
            barcode,
            name or "",
            brand or "",
            category or "",
            self.format_price(price),
            quantity or 0
        )

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
        barcode = self.require_barcode()
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
        barcode = self.require_barcode()
        if not barcode:
            return

        self.cur.execute("SELECT id, price FROM products WHERE barcode = ?", (barcode,))
        res = self.cur.fetchone()

        if not res:
            messagebox.showerror("Klaida", "Prekė nerasta")
            return

        product_id, saved_price = res

        price = self.get_price_value(default=saved_price or 0.0)
        if price is None:
            return

        if self.get_existing_quantity(product_id) <= 0:
            messagebox.showerror("Klaida", "Šios prekės sandėlyje nėra")
            return

        self.cur.execute("""
        UPDATE inventory
        SET quantity = quantity - 1,
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
            messagebox.showerror("Klaida", "Pasirinkite prekę redagavimui")
            return

        barcode = self.require_barcode()
        if not barcode:
            return

        price = self.get_price_value()
        if price is None:
            return

        try:
            self.cur.execute("""
            UPDATE products
            SET barcode = ?, name = ?, brand = ?, category = ?, price = ?
            WHERE id = ?
            """, (
                barcode,
                self.name.get().strip(),
                self.brand.get().strip(),
                self.category.get().strip(),
                price,
                self.selected_product_id
            ))
        except sqlite3.IntegrityError:
            messagebox.showerror("Klaida", "Toks barkodas jau naudojamas")
            return

        self.conn.commit()
        self.load_inventory()
        self.clear_inputs()
        self.selected_product_id = None

    # ---------------- DELETE ----------------
    def delete_product(self):
        if not self.selected_product_id:
            messagebox.showerror("Klaida", "Pasirinkite prekę trynimui")
            return

        if not messagebox.askyesno("Patvirtinimas", "Ištrinti šią prekę?"):
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
        query = self.search_query.get().strip()

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
            self.tree.insert("", tk.END, values=self.format_inventory_row(row))

    def clear_search(self):
        self.search_query.delete(0, tk.END)
        self.load_inventory()

    # ---------------- CSV ----------------
    def export_csv(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Eksportuoti inventorių"
        )
        if not path:
            return

        self.cur.execute("""
        SELECT p.barcode, p.name, p.brand, p.category, p.price, COALESCE(i.quantity, 0)
        FROM products p
        LEFT JOIN inventory i ON p.id = i.product_id
        ORDER BY p.name
        """)

        with open(path, "w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(["barcode", "name", "brand", "category", "price", "quantity"])
            writer.writerows(self.cur.fetchall())

        messagebox.showinfo("Eksportas", "CSV failas išsaugotas")

    def import_csv(self):
        path = filedialog.askopenfilename(
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Importuoti inventorių"
        )
        if not path:
            return

        imported = 0
        skipped = 0

        try:
            with open(path, newline="", encoding="utf-8-sig") as csv_file:
                reader = csv.DictReader(csv_file)
                required = {"barcode", "name", "brand", "category", "price", "quantity"}
                if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
                    messagebox.showerror(
                        "Klaida",
                        "CSV turi turėti stulpelius: barcode, name, brand, category, price, quantity"
                    )
                    return

                for row in reader:
                    barcode = (row.get("barcode") or "").strip()
                    if not barcode:
                        skipped += 1
                        continue

                    try:
                        price = float((row.get("price") or "0").strip().replace(",", "."))
                        quantity = int((row.get("quantity") or "0").strip())
                    except ValueError:
                        skipped += 1
                        continue

                    if price < 0 or quantity < 0:
                        skipped += 1
                        continue

                    self.cur.execute("SELECT id FROM products WHERE barcode = ?", (barcode,))
                    existing = self.cur.fetchone()

                    if existing:
                        product_id = existing[0]
                        self.cur.execute("""
                        UPDATE products
                        SET name = ?, brand = ?, category = ?, price = ?
                        WHERE id = ?
                        """, (
                            (row.get("name") or "").strip(),
                            (row.get("brand") or "").strip(),
                            (row.get("category") or "").strip(),
                            price,
                            product_id
                        ))
                    else:
                        self.cur.execute("""
                        INSERT INTO products (barcode, name, brand, category, price)
                        VALUES (?, ?, ?, ?, ?)
                        """, (
                            barcode,
                            (row.get("name") or "").strip(),
                            (row.get("brand") or "").strip(),
                            (row.get("category") or "").strip(),
                            price
                        ))
                        product_id = self.cur.lastrowid

                    self.cur.execute("""
                    INSERT INTO inventory (product_id, quantity, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(product_id) DO UPDATE SET
                        quantity = excluded.quantity,
                        updated_at = CURRENT_TIMESTAMP
                    """, (product_id, quantity))
                    imported += 1
        except OSError as exc:
            messagebox.showerror("Klaida", f"Nepavyko atidaryti CSV failo:\n{exc}")
            return

        self.conn.commit()
        self.load_inventory()
        messagebox.showinfo("Importas", f"Importuota: {imported}\nPraleista: {skipped}")

    # ---------------- SUMMARY ----------------
    def show_monthly_summary(self):
        now = datetime.now()
        month_start = now.strftime("%Y-%m-01")
        next_month = f"{now.year + (1 if now.month == 12 else 0):04d}-{1 if now.month == 12 else now.month + 1:02d}-01"

        self.cur.execute("""
        SELECT
            COALESCE(p.name, s.barcode) AS product_name,
            s.barcode,
            SUM(s.quantity) AS sold_qty,
            SUM(s.quantity * s.sold_price) AS revenue
        FROM sales s
        LEFT JOIN products p ON p.id = s.product_id
        WHERE s.created_at >= ? AND s.created_at < ?
        GROUP BY s.product_id, s.barcode
        ORDER BY revenue DESC
        """, (month_start, next_month))
        rows = self.cur.fetchall()

        total_quantity = sum(row[2] or 0 for row in rows)
        total_revenue = sum(row[3] or 0 for row in rows)

        win = tk.Toplevel(self.root)
        win.title("Mėnesio suvestinė")
        win.geometry("700x420")
        win.transient(self.root)

        header = ttk.Frame(win, padding=10)
        header.pack(fill=tk.X)
        ttk.Label(
            header,
            text=f"{now.strftime('%Y-%m')} pardavimai: {total_quantity} vnt. / {self.format_price(total_revenue)}"
        ).pack(side=tk.LEFT)

        cols = ("name", "barcode", "quantity", "revenue")
        tree = ttk.Treeview(win, columns=cols, show="headings")
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        headings = {
            "name": "Prekė",
            "barcode": "Barcode",
            "quantity": "Kiekis",
            "revenue": "Suma"
        }
        for col in cols:
            tree.heading(col, text=headings[col])
            tree.column(col, width=160 if col in ("name", "barcode") else 90)

        for name, barcode, quantity, revenue in rows:
            tree.insert("", tk.END, values=(name or "", barcode, quantity or 0, self.format_price(revenue)))

        if not rows:
            tree.insert("", tk.END, values=("Pardavimų šį mėnesį nėra", "", 0, self.format_price(0)))


if __name__ == "__main__":
    root = tk.Tk()
    app = InventoryApp(root)
    root.mainloop()
