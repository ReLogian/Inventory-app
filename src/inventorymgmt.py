import csv
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import ttk, messagebox, filedialog
import sqlite3
import os
import subprocess
import sys
import threading
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent
DB_PATH = APP_DIR / "inventory.db"

os.chdir(APP_DIR)

CATEGORY_FILTER_ALL = "Visos kategorijos"
COMMON_CATEGORIES = (
    "Apsauginis stiklas",
    "Apsaugine plevele",
    "Atminties kortele",
    "Ausines",
    "Baterija",
    "Deklas",
    "Garso koloneles",
    "Ikroviklis",
    "Kamera",
    "Laidas",
    "Laikiklis",
    "Laikrodis",
    "Moduliatorius",
    "Power bank",
    "USB atmintukas",
)


def create_schema(conn):
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        barcode TEXT UNIQUE,
        name TEXT,
        brand TEXT,
        category TEXT,
        price REAL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        product_id INTEGER PRIMARY KEY,
        quantity INTEGER DEFAULT 0,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER,
        barcode TEXT,
        quantity INTEGER,
        sold_price REAL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()


def fetch_categories(cur):
    cur.execute("""
    SELECT DISTINCT category
    FROM products
    WHERE category IS NOT NULL AND TRIM(category) != ''
    ORDER BY category
    """)
    return [row[0] for row in cur.fetchall()]


def fetch_inventory_rows(cur):
    cur.execute("""
    SELECT p.barcode, p.name, p.brand, p.category, p.price, i.quantity
    FROM products p
    LEFT JOIN inventory i ON p.id = i.product_id
    ORDER BY p.name
    """)
    return cur.fetchall()


def fetch_filtered_inventory_rows(cur, query="", category=CATEGORY_FILTER_ALL):
    clauses = []
    params = []

    if query:
        like = f"%{query}%"
        clauses.append("""
        (
            p.barcode LIKE ?
            OR p.name LIKE ?
            OR p.brand LIKE ?
            OR p.category LIKE ?
        )
        """)
        params.extend((like, like, like, like))

    if category and category != CATEGORY_FILTER_ALL:
        clauses.append("p.category = ?")
        params.append(category)

    sql = """
    SELECT p.barcode, p.name, p.brand, p.category, p.price, i.quantity
    FROM products p
    LEFT JOIN inventory i ON p.id = i.product_id
    """
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY p.name"

    cur.execute(sql, params)
    return cur.fetchall()


def fetch_sales_summary_rows(cur, start_date, end_date):
    cur.execute("""
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
    """, (start_date, end_date))
    return cur.fetchall()


class InventoryApp:
    CATEGORY_FILTER_ALL = CATEGORY_FILTER_ALL
    COMMON_CATEGORIES = COMMON_CATEGORIES

    def __init__(self, root):
        self.root = root
        self.root.title("Inventorius")
        self.root.geometry("1150x700")
        self.root.minsize(950, 600)
        self.set_window_icon()

        # ---------------- DB ----------------
        self.conn = sqlite3.connect(DB_PATH)
        self.cur = self.conn.cursor()
        self.create_tables()

        self.selected_product_id = None

        style = ttk.Style()
        style.configure("Treeview", rowheight=26)

        # ---------------- INPUTS ----------------
        self.top = ttk.LabelFrame(root, text="Prekės informacija", padding=10)
        self.top_visible = True
        self.top_pack_options = {"fill": tk.X, "padx": 12, "pady": (12, 6)}
        self.top.pack(**self.top_pack_options)

        self.barcode = self._entry(self.top, "Barcode", 0)
        self.name = self._entry(self.top, "Name", 1)
        self.brand = self._entry(self.top, "Brand", 2)
        self.category = self._category_combobox(self.top, "Category", 3)
        self.price = self._entry(self.top, "Price", 4)
        ttk.Button(self.top, text="▼", width=3, command=self.hide_product_form).grid(
            row=1, column=5, padx=(8, 0), pady=(4, 0)
        )

        for col in range(6):
            self.top.columnconfigure(col, weight=1)

        self.hide_product_form()

        # ---------------- BUTTONS ----------------
        self.buttons_frame = ttk.Frame(root)
        self.buttons_frame.pack(fill=tk.X, padx=12, pady=6)

        ttk.Button(self.buttons_frame, text="Pridėti", command=self.add_stock).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(self.buttons_frame, text="Atimti", command=self.remove_stock).pack(side=tk.LEFT, padx=6)
        ttk.Button(self.buttons_frame, text="Redaguoti", command=self.edit_product).pack(side=tk.LEFT, padx=6)
        ttk.Button(self.buttons_frame, text="Ištrinti", command=self.delete_product).pack(side=tk.LEFT, padx=6)
        ttk.Button(self.buttons_frame, text="Atnaujinti", command=self.load_inventory).pack(side=tk.LEFT, padx=6)
        ttk.Button(
            self.buttons_frame,
            text="Eksportuoti CSV",
            command=self.export_csv
        ).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(self.buttons_frame, text="Importuoti CSV", command=self.import_csv).pack(side=tk.RIGHT, padx=6)
        ttk.Button(
            self.buttons_frame,
            text="Mėnesio suvestinė",
            command=self.show_monthly_summary
        ).pack(side=tk.RIGHT, padx=6)
        ttk.Button(
            self.buttons_frame,
            text="Dienos suvestinė",
            command=self.show_daily_summary
        ).pack(side=tk.RIGHT, padx=6)

        # ---------------- SEARCH ----------------
        search_frame = ttk.LabelFrame(root, text="Paieška", padding=10)
        search_frame.pack(fill=tk.X, padx=12, pady=6)

        ttk.Label(search_frame, text="Ieškoti").pack(side=tk.LEFT)
        self.search_query = ttk.Entry(search_frame)
        self.search_query.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        ttk.Label(search_frame, text="Kategorija").pack(side=tk.LEFT, padx=(8, 0))
        self.category_filter_var = tk.StringVar(value=self.CATEGORY_FILTER_ALL)
        self.category_filter = ttk.Combobox(
            search_frame,
            textvariable=self.category_filter_var,
            state="readonly",
            width=22
        )
        self.category_filter.pack(side=tk.LEFT, padx=8)
        self.category_filter.bind("<<ComboboxSelected>>", lambda e: self.search())
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

        self.refresh_categories()
        self.load_inventory()
        self.root.after(1000, self.check_for_updates)

    # ---------------- DB ----------------
    def create_tables(self):
        create_schema(self.conn)

    # ---------------- HELPERS ----------------
    def _entry(self, parent, label, col):
        ttk.Label(parent, text=label).grid(row=0, column=col)
        e = ttk.Entry(parent, width=18)
        e.grid(row=1, column=col, padx=5, pady=(4, 0), sticky="ew")
        return e

    def _category_combobox(self, parent, label, col):
        ttk.Label(parent, text=label).grid(row=0, column=col)
        combo = ttk.Combobox(parent, width=18, values=self.COMMON_CATEGORIES)
        combo.grid(row=1, column=col, padx=5, pady=(4, 0), sticky="ew")
        return combo

    def get_category_value(self):
        return self.category.get().strip()

    def set_window_icon(self):
        ico_candidates = (
            APP_DIR / "app.ico",
            APP_DIR / "assets" / "app.ico",
            PROJECT_DIR / "app.ico",
        )
        for path in ico_candidates:
            if path.exists():
                try:
                    self.root.iconbitmap(str(path))
                except tk.TclError:
                    try:
                        icon = tk.PhotoImage(file=str(path))
                        self.root.iconphoto(True, icon)
                        self.window_icon = icon
                    except tk.TclError:
                        pass
                    else:
                        return
                else:
                    return

        png_candidates = (
            APP_DIR / "app.png",
            APP_DIR / "assets" / "app.png",
            PROJECT_DIR / "app.png",
        )
        for path in png_candidates:
            if path.exists():
                try:
                    icon = tk.PhotoImage(file=str(path))
                    self.root.iconphoto(True, icon)
                    self.window_icon = icon
                except tk.TclError:
                    pass
                else:
                    return

    def show_product_form(self):
        if not self.top_visible:
            self.top.pack(**self.top_pack_options, before=self.buttons_frame)
            self.top_visible = True
        self.barcode.focus_set()

    def hide_product_form(self):
        if self.top_visible:
            self.top.pack_forget()
            self.top_visible = False

    def check_for_updates(self):
        thread = threading.Thread(target=self._check_for_updates_worker, daemon=True)
        thread.start()

    def _run_git(self, *args):
        git_executable = self.find_git_executable()
        if not git_executable:
            raise FileNotFoundError("Git executable not found")

        startupinfo = None
        if sys.platform.startswith("win"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        return subprocess.run(
            (git_executable, *args),
            cwd=PROJECT_DIR,
            text=True,
            capture_output=True,
            startupinfo=startupinfo,
            check=False
        )

    def find_git_executable(self):
        windows_candidates = (
            PROJECT_DIR / "PortableGit" / "cmd" / "git.exe",
            PROJECT_DIR / "Git" / "cmd" / "git.exe",
            APP_DIR / "PortableGit" / "cmd" / "git.exe",
            APP_DIR / "Git" / "cmd" / "git.exe",
        )
        for path in windows_candidates:
            if path.exists():
                return str(path)
        return "git"

    def _check_for_updates_worker(self):
        try:
            inside_repo = self._run_git("rev-parse", "--is-inside-work-tree")
            if inside_repo.returncode != 0 or inside_repo.stdout.strip() != "true":
                return

            upstream = self._run_git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
            if upstream.returncode != 0:
                return

            if self._run_git("fetch", "--quiet").returncode != 0:
                return

            behind = self._run_git("rev-list", "--count", "HEAD..@{u}")
            if behind.returncode != 0:
                return

            commits_behind = int(behind.stdout.strip() or "0")
            if commits_behind > 0:
                self.root.after(0, lambda: self.prompt_update(commits_behind))
        except (OSError, ValueError, subprocess.SubprocessError):
            return

    def prompt_update(self, commits_behind):
        should_update = messagebox.askyesno(
            "Nauja versija",
            f"Yra nauja versija ({commits_behind} pakeitimai). Atnaujinti dabar?"
        )
        if not should_update:
            return

        thread = threading.Thread(target=self._pull_updates_worker, daemon=True)
        thread.start()

    def _pull_updates_worker(self):
        result = self._run_git("pull", "--ff-only")
        self.root.after(0, lambda: self.show_update_result(result.returncode, result.stderr.strip()))

    def show_update_result(self, returncode, error):
        if returncode == 0:
            messagebox.showinfo(
                "Atnaujinta",
                "Programa atnaujinta. Uždarykite ir paleiskite iš naujo, kad įsijungtų nauja versija."
            )
        else:
            messagebox.showerror(
                "Atnaujinti nepavyko",
                error or "Nepavyko atnaujinti programos iš Git."
            )

    def refresh_categories(self):
        db_categories = fetch_categories(self.cur)
        categories = sorted(set(self.COMMON_CATEGORIES).union(db_categories), key=str.lower)
        self.category.configure(values=categories)

        selected_filter = self.category_filter_var.get()
        filter_values = [self.CATEGORY_FILTER_ALL] + categories
        self.category_filter.configure(values=filter_values)
        if selected_filter in filter_values:
            self.category_filter_var.set(selected_filter)
        else:
            self.category_filter_var.set(self.CATEGORY_FILTER_ALL)

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

        self.show_product_form()
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
    def load_inventory(self, clear_filters=True):
        if clear_filters:
            self.search_query.delete(0, tk.END)
            self.category_filter_var.set(self.CATEGORY_FILTER_ALL)
        self.tree.delete(*self.tree.get_children())

        for row in fetch_inventory_rows(self.cur):
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
        if not self.top_visible:
            self.show_product_form()
            return

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
            """, (barcode, self.name.get(), self.brand.get(), self.get_category_value(), price))
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
        self.refresh_categories()
        self.load_inventory()
        self.clear_inputs()
        self.hide_product_form()

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
        self.hide_product_form()

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
                self.get_category_value(),
                price,
                self.selected_product_id
            ))
        except sqlite3.IntegrityError:
            messagebox.showerror("Klaida", "Toks barkodas jau naudojamas")
            return

        self.conn.commit()
        self.refresh_categories()
        self.load_inventory()
        self.clear_inputs()
        self.selected_product_id = None
        self.hide_product_form()

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
        self.refresh_categories()
        self.load_inventory()
        self.clear_inputs()
        self.hide_product_form()

    # ---------------- SEARCH ----------------
    def search(self):
        query = self.search_query.get().strip()
        category = self.category_filter_var.get().strip()

        self.tree.delete(*self.tree.get_children())

        if not query and category == self.CATEGORY_FILTER_ALL:
            self.load_inventory(clear_filters=False)
            return

        for row in fetch_filtered_inventory_rows(self.cur, query, category):
            self.tree.insert("", tk.END, values=self.format_inventory_row(row))

    def clear_search(self):
        self.search_query.delete(0, tk.END)
        self.category_filter_var.set(self.CATEGORY_FILTER_ALL)
        self.load_inventory(clear_filters=False)

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
        self.refresh_categories()
        self.load_inventory()
        messagebox.showinfo("Importas", f"Importuota: {imported}\nPraleista: {skipped}")

    # ---------------- SUMMARY ----------------
    def show_daily_summary(self):
        now = datetime.now()
        day_start = now.strftime("%Y-%m-%d 00:00:00")
        day_end = (datetime(now.year, now.month, now.day) + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
        self.show_sales_summary(
            "Dienos suvestinė",
            f"{now.strftime('%Y-%m-%d')} pardavimai",
            day_start,
            day_end,
            "Pardavimų šiandien nėra"
        )

    def show_monthly_summary(self):
        now = datetime.now()
        month_start = now.strftime("%Y-%m-01")
        next_month = f"{now.year + (1 if now.month == 12 else 0):04d}-{1 if now.month == 12 else now.month + 1:02d}-01"
        self.show_sales_summary(
            "Mėnesio suvestinė",
            f"{now.strftime('%Y-%m')} pardavimai",
            month_start,
            next_month,
            "Pardavimų šį mėnesį nėra"
        )

    def show_sales_summary(self, title, label, start_date, end_date, empty_message):
        rows = fetch_sales_summary_rows(self.cur, start_date, end_date)

        total_quantity = sum(row[2] or 0 for row in rows)
        total_revenue = sum(row[3] or 0 for row in rows)

        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry("700x420")
        win.transient(self.root)

        header = ttk.Frame(win, padding=10)
        header.pack(fill=tk.X)
        ttk.Label(
            header,
            text=f"{label}: {total_quantity} vnt. / {self.format_price(total_revenue)}"
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
            tree.insert("", tk.END, values=(empty_message, "", 0, self.format_price(0)))


if __name__ == "__main__":
    root = tk.Tk()
    app = InventoryApp(root)
    root.mainloop()
