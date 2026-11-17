import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageTk, ImageOps
import sqlite3
import os
import hashlib
import secrets
from datetime import datetime

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ==================================================
# SETTINGS
# ==================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_FOLDER = os.path.join(BASE_DIR, "Images", "restaurants")
DB_PATH = os.path.join(BASE_DIR, "foodiehub.db")

BG = "#f5f5f5"
ORANGE = "#ff6b35"
DARK = "#222222"

cart = {}
current_user = None
restaurant_images = []

ADMIN_EMAIL = "admin@foodiehub.com"
ADMIN_PASSWORD = "Admin123!"

# Initial data is inserted only if the restaurant table is empty.
DEFAULT_RESTAURANTS = [
    {
        "name": "Spice Garden",
        "category": "Biryani, North Indian",
        "rating": "4.5",
        "time": "30-35 min",
        "image": "spice.jpeg",
        "menu": [
            ("Chicken Biryani", 220),
            ("Veg Biryani", 160),
            ("Paneer Butter Masala", 190),
            ("Butter Naan", 40),
            ("Chicken 65", 180)
        ]
    },
    {
        "name": "Pizza Palace",
        "category": "Pizza, Italian",
        "rating": "4.3",
        "time": "25-30 min",
        "image": "pizza.jpeg",
        "menu": [
            ("Margherita Pizza", 180),
            ("Cheese Pizza", 220),
            ("Farmhouse Pizza", 260),
            ("Garlic Bread", 100),
            ("Veg Burger", 120)
        ]
    },
    {
        "name": "Burger House",
        "category": "Burgers, Fast Food",
        "rating": "4.2",
        "time": "20-25 min",
        "image": "burger.jpeg",
        "menu": [
            ("Classic Burger", 100),
            ("Cheese Burger", 120),
            ("Veg Burger", 90),
            ("French Fries", 80),
            ("Paneer Burger", 140)
        ]
    }
]

# ==================================================
# DATABASE
# ==================================================

def get_connection():
    return sqlite3.connect(DB_PATH)


def initialize_database():
    con = get_connection()
    cur = con.cursor()

    # Existing tables: retained without deleting customer/order data.
    cur.execute(""" CREATE TABLE IF NOT EXISTS customers ( id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, phone TEXT NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL ) """)

    cur.execute(""" CREATE TABLE IF NOT EXISTS orders ( id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER NOT NULL, address TEXT NOT NULL, total REAL NOT NULL, status TEXT DEFAULT 'Order Placed', order_date TEXT NOT NULL, FOREIGN KEY(customer_id) REFERENCES customers(id) ) """)

    cur.execute(""" CREATE TABLE IF NOT EXISTS order_items ( id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL, restaurant TEXT NOT NULL, item_name TEXT NOT NULL, price REAL NOT NULL, quantity INTEGER NOT NULL, FOREIGN KEY(order_id) REFERENCES orders(id) ) """)

    # Additive migrations: keep all existing customer/order records intact.
    order_columns = [row[1] for row in cur.execute("PRAGMA table_info(orders)").fetchall()]
    if "payment_method" not in order_columns:
        cur.execute("ALTER TABLE orders ADD COLUMN payment_method TEXT DEFAULT 'Cash on Delivery'")
    if "payment_status" not in order_columns:
        cur.execute("ALTER TABLE orders ADD COLUMN payment_status TEXT DEFAULT 'Pending'")

    cur.execute(""" CREATE TABLE IF NOT EXISTS reviews ( id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL UNIQUE, customer_id INTEGER NOT NULL, restaurant TEXT NOT NULL, rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5), comment TEXT, review_date TEXT NOT NULL, FOREIGN KEY(order_id) REFERENCES orders(id), FOREIGN KEY(customer_id) REFERENCES customers(id) ) """)

    # New Stage 5 tables.
    cur.execute(""" CREATE TABLE IF NOT EXISTS restaurants ( id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, category TEXT NOT NULL, rating TEXT NOT NULL, delivery_time TEXT NOT NULL, image TEXT NOT NULL ) """)

    cur.execute(""" CREATE TABLE IF NOT EXISTS menu_items ( id INTEGER PRIMARY KEY AUTOINCREMENT, restaurant_id INTEGER NOT NULL, name TEXT NOT NULL, price REAL NOT NULL CHECK(price >= 0), FOREIGN KEY(restaurant_id) REFERENCES restaurants(id) ON DELETE CASCADE ) """)

    # Seed the original three restaurants and menus only once.
    restaurant_count = cur.execute(
        "SELECT COUNT(*) FROM restaurants"
    ).fetchone()[0]

    if restaurant_count == 0:
        for restaurant in DEFAULT_RESTAURANTS:
            cur.execute(""" INSERT INTO restaurants (name, category, rating, delivery_time, image) VALUES (?, ?, ?, ?, ?) """, (
                restaurant["name"],
                restaurant["category"],
                restaurant["rating"],
                restaurant["time"],
                restaurant["image"]
            ))
            restaurant_id = cur.lastrowid

            for item_name, price in restaurant["menu"]:
                cur.execute(""" INSERT INTO menu_items (restaurant_id, name, price) VALUES (?, ?, ?) """, (restaurant_id, item_name, price))

    con.commit()
    con.close()


def hash_password(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        bytes.fromhex(salt),
        100000
    ).hex()


def get_restaurants():
    con = get_connection()
    rows = con.execute(""" SELECT id, name, category, rating, delivery_time, image FROM restaurants ORDER BY id """).fetchall()

    result = []
    for restaurant_id, name, category, rating, delivery_time, image in rows:
        menu_rows = con.execute(""" SELECT id, name, price FROM menu_items WHERE restaurant_id = ? ORDER BY id """, (restaurant_id,)).fetchall()

        result.append({
            "id": restaurant_id,
            "name": name,
            "category": category,
            "rating": rating,
            "time": delivery_time,
            "image": image,
            "menu": [
                {"id": item_id, "name": item_name, "price": price}
                for item_id, item_name, price in menu_rows
            ]
        })

    con.close()
    return result


# ==================================================
# MAIN WINDOW
# ==================================================

root = tk.Tk()
root.title("FoodieHub - Online Food Ordering")
root.geometry("1050x750")
root.minsize(850, 600)
root.configure(bg=BG)


def clear_window():
    for widget in root.winfo_children():
        widget.destroy()


# ==================================================
# REGISTRATION
# ==================================================

def show_registration():
    clear_window()

    tk.Label(
        root, text="FoodieHub",
        font=("Arial", 28, "bold"),
        bg=BG, fg=ORANGE
    ).pack(pady=25)

    tk.Label(
        root, text="Create Your Account",
        font=("Arial", 21, "bold"), bg=BG
    ).pack(pady=10)

    form = tk.Frame(root, bg="white", padx=35, pady=25)
    form.pack()

    fields = {}

    for label in ["Full Name", "Email", "Phone Number", "Password"]:
        tk.Label(
            form, text=label,
            font=("Arial", 11, "bold"), bg="white"
        ).pack(anchor="w", pady=(8, 3))

        entry = tk.Entry(
            form, width=32, font=("Arial", 12),
            show="*" if label == "Password" else ""
        )
        entry.pack(ipady=6)
        fields[label] = entry

    def register():
        name = fields["Full Name"].get().strip()
        email = fields["Email"].get().strip().lower()
        phone = fields["Phone Number"].get().strip()
        password = fields["Password"].get()

        if not all([name, email, phone, password]):
            messagebox.showwarning("Missing Details", "Fill in all fields.")
            return

        if "@" not in email or "." not in email:
            messagebox.showwarning("Invalid Email", "Enter a valid email.")
            return

        if not phone.isdigit() or len(phone) < 10:
            messagebox.showwarning("Invalid Phone", "Enter a valid phone number.")
            return

        if len(password) < 6:
            messagebox.showwarning("Password", "Use at least 6 characters.")
            return

        salt = secrets.token_hex(16)
        password_hash = hash_password(password, salt)

        con = get_connection()
        try:
            con.execute(""" INSERT INTO customers (name, email, phone, salt, password_hash) VALUES (?, ?, ?, ?, ?) """, (name, email, phone, salt, password_hash))
            con.commit()

            messagebox.showinfo("Success", "Account created. Please log in.")
            show_login()

        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Email already registered.")

        finally:
            con.close()

    tk.Button(
        root, text="Register",
        bg=ORANGE, fg="white",
        font=("Arial", 12, "bold"),
        command=register, relief="flat"
    ).pack(pady=15, ipadx=25, ipady=7)

    tk.Button(
        root, text="Already registered? Login",
        bg=BG, relief="flat", command=show_login
    ).pack()


# ==================================================
# CUSTOMER LOGIN
# ==================================================

def show_login():
    clear_window()

    tk.Label(
        root, text="FoodieHub",
        font=("Arial", 32, "bold"),
        bg=BG, fg=ORANGE
    ).pack(pady=(65, 10))

    tk.Label(
        root, text="Customer Login",
        font=("Arial", 21, "bold"), bg=BG
    ).pack(pady=20)

    form = tk.Frame(root, bg="white", padx=35, pady=25)
    form.pack()

    tk.Label(form, text="Email", bg="white").pack(anchor="w")
    email_entry = tk.Entry(form, width=32, font=("Arial", 12))
    email_entry.pack(pady=7, ipady=5)

    tk.Label(form, text="Password", bg="white").pack(anchor="w")
    password_entry = tk.Entry(
        form, width=32, font=("Arial", 12), show="*"
    )
    password_entry.pack(pady=7, ipady=5)

    def login():
        global current_user

        email = email_entry.get().strip().lower()
        password = password_entry.get()

        if not email or not password:
            messagebox.showwarning("Missing Details", "Enter login details.")
            return

        con = get_connection()
        customer = con.execute(""" SELECT id, name, salt, password_hash FROM customers WHERE email = ? """, (email,)).fetchone()
        con.close()

        if customer:
            customer_id, name, salt, saved_hash = customer
            entered_hash = hash_password(password, salt)

            if secrets.compare_digest(entered_hash, saved_hash):
                current_user = {"id": customer_id, "name": name}
                show_home()
                return

        messagebox.showerror("Login Failed", "Incorrect email or password.")

    tk.Button(
        form, text="Login",
        bg=ORANGE, fg="white",
        font=("Arial", 12, "bold"),
        relief="flat", command=login
    ).pack(pady=12, ipadx=25, ipady=6)

    tk.Button(
        root, text="Create a new account",
        bg=BG, relief="flat", command=show_registration
    ).pack(pady=10)

    tk.Button(
        root, text="Forgot Password?",
        bg=BG, fg=ORANGE, relief="flat",
        font=("Arial", 10, "underline"),
        command=show_forgot_password
    ).pack(pady=2)

    tk.Button(
        root, text="Admin Login",
        bg=DARK, fg="white",
        relief="flat", command=show_admin_login
    ).pack(pady=8, ipadx=20, ipady=5)


def show_forgot_password():
    """Reset a customer's password after matching their registered email and phone."""
    window = tk.Toplevel(root)
    window.title("Forgot Password - FoodieHub")
    window.geometry("460x560")
    window.configure(bg=BG)
    window.transient(root)
    window.grab_set()

    tk.Label(
        window, text="Reset Your Password",
        font=("Arial", 21, "bold"), bg=BG, fg=ORANGE
    ).pack(pady=(25, 8))

    tk.Label(
        window,
        text="Enter your registered email and phone number to verify your account.",
        font=("Arial", 10), bg=BG, fg="#555555",
        wraplength=380, justify="center"
    ).pack(pady=(0, 15))

    form = tk.Frame(window, bg="white", padx=28, pady=20)
    form.pack(padx=25, fill="x")

    entries = {}
    fields = [
        ("Registered Email", "email", False),
        ("Registered Phone Number", "phone", False),
        ("New Password", "password", True),
        ("Confirm New Password", "confirm", True),
    ]

    for label, key, hidden in fields:
        tk.Label(
            form, text=label, font=("Arial", 10, "bold"), bg="white"
        ).pack(anchor="w", pady=(8, 3))
        entry = tk.Entry(
            form, width=34, font=("Arial", 11),
            show="*" if hidden else ""
        )
        entry.pack(ipady=5)
        entries[key] = entry

    def reset_password():
        email = entries["email"].get().strip().lower()
        phone = entries["phone"].get().strip()
        new_password = entries["password"].get()
        confirm_password = entries["confirm"].get()

        if not all([email, phone, new_password, confirm_password]):
            messagebox.showwarning(
                "Missing Details", "Please fill in all fields.", parent=window
            )
            return

        if not phone.isdigit() or len(phone) < 10:
            messagebox.showwarning(
                "Invalid Phone", "Enter the phone number registered with your account.",
                parent=window
            )
            return

        if len(new_password) < 6:
            messagebox.showwarning(
                "Weak Password", "Password must contain at least 6 characters.",
                parent=window
            )
            return

        if new_password != confirm_password:
            messagebox.showerror(
                "Password Mismatch", "The two passwords do not match.",
                parent=window
            )
            return

        con = get_connection()
        try:
            customer = con.execute(
                "SELECT id FROM customers WHERE email = ? AND phone = ?",
                (email, phone)
            ).fetchone()

            if not customer:
                messagebox.showerror(
                    "Verification Failed",
                    "The email and phone number do not match a registered account.",
                    parent=window
                )
                return

            salt = secrets.token_hex(16)
            password_hash = hash_password(new_password, salt)

            con.execute(
                "UPDATE customers SET salt = ?, password_hash = ? WHERE id = ?",
                (salt, password_hash, customer[0])
            )
            con.commit()

            messagebox.showinfo(
                "Password Updated",
                "Your password has been reset successfully. Please log in with your new password.",
                parent=window
            )
            window.destroy()

        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error", "Could not reset password: " + str(error),
                parent=window
            )
        finally:
            con.close()

    tk.Button(
        window, text="Reset Password",
        bg=ORANGE, fg="white", font=("Arial", 11, "bold"),
        relief="flat", command=reset_password
    ).pack(pady=18, ipadx=20, ipady=7)

    tk.Button(
        window, text="Back to Login",
        bg=DARK, fg="white", relief="flat",
        command=window.destroy
    ).pack(pady=3, ipadx=15, ipady=6)


# ==================================================
# ADMIN LOGIN
# ==================================================

def show_admin_login():
    clear_window()

    tk.Label(
        root, text="FoodieHub Admin",
        font=("Arial", 27, "bold"),
        bg=BG, fg=ORANGE
    ).pack(pady=40)

    form = tk.Frame(root, bg="white", padx=35, pady=25)
    form.pack()

    tk.Label(form, text="Admin Email", bg="white").pack(anchor="w")
    email_entry = tk.Entry(form, width=32, font=("Arial", 12))
    email_entry.pack(pady=8, ipady=5)
    email_entry.insert(0, ADMIN_EMAIL)

    tk.Label(form, text="Admin Password", bg="white").pack(anchor="w")
    password_entry = tk.Entry(
        form, width=32, font=("Arial", 12), show="*"
    )
    password_entry.pack(pady=8, ipady=5)

    def admin_login():
        if (
            email_entry.get().strip().lower() == ADMIN_EMAIL
            and password_entry.get() == ADMIN_PASSWORD
        ):
            show_admin_dashboard()
        else:
            messagebox.showerror("Login Failed", "Invalid admin credentials.")

    tk.Button(
        form, text="Login as Admin",
        bg=ORANGE, fg="white",
        font=("Arial", 12, "bold"),
        relief="flat", command=admin_login
    ).pack(pady=15, ipadx=15, ipady=6)

    tk.Button(
        root, text="Back to Customer Login",
        bg=BG, relief="flat", command=show_login
    ).pack(pady=15)


# ==================================================
# STAGE 6: SALES ANALYTICS
# ==================================================

def show_sales_analytics():
    window = tk.Toplevel(root)
    window.title("FoodieHub - Sales Analytics")
    window.geometry("1100x780")
    window.configure(bg=BG)

    tk.Label(
        window, text="Sales Analytics",
        font=("Arial", 22, "bold"), bg=BG
    ).pack(pady=15)

    con = get_connection()
    cur = con.cursor()

    daily_rows = cur.execute(""" SELECT substr(order_date, 1, 10) AS order_day, COALESCE(SUM(total), 0) FROM orders WHERE status != 'Cancelled' GROUP BY order_day ORDER BY order_day """).fetchall()

    popular_rows = cur.execute(""" SELECT item_name, SUM(quantity) AS total_quantity FROM order_items JOIN orders ON orders.id = order_items.order_id WHERE orders.status != 'Cancelled' GROUP BY item_name ORDER BY total_quantity DESC LIMIT 8 """).fetchall()

    con.close()

    chart_area = tk.Frame(window, bg=BG)
    chart_area.pack(fill="both", expand=True, padx=15, pady=10)

    revenue_frame = tk.Frame(chart_area, bg="white")
    revenue_frame.pack(fill="both", expand=True, padx=5, pady=6)

    if daily_rows:
        dates = [row[0] for row in daily_rows]
        revenues = [float(row[1] or 0) for row in daily_rows]

        revenue_figure = Figure(figsize=(9, 2.6), dpi=100)
        revenue_axis = revenue_figure.add_subplot(111)
        revenue_axis.plot(dates, revenues, marker="o")
        revenue_axis.set_title("Revenue by Order Date")
        revenue_axis.set_xlabel("Order Date")
        revenue_axis.set_ylabel("Revenue (₹)")
        revenue_axis.tick_params(axis="x", rotation=30)
        revenue_figure.tight_layout()

        revenue_canvas = FigureCanvasTkAgg(
            revenue_figure, master=revenue_frame
        )
        revenue_canvas.draw()
        revenue_canvas.get_tk_widget().pack(fill="both", expand=True)
    else:
        tk.Label(
            revenue_frame,
            text="No order data yet. Revenue chart will appear after orders are placed.",
            bg="white", font=("Arial", 11)
        ).pack(pady=35)

    popular_frame = tk.Frame(chart_area, bg="white")
    popular_frame.pack(fill="both", expand=True, padx=5, pady=6)

    if popular_rows:
        item_names = [row[0] for row in popular_rows]
        quantities = [int(row[1]) for row in popular_rows]

        popular_figure = Figure(figsize=(9, 2.6), dpi=100)
        popular_axis = popular_figure.add_subplot(111)
        popular_axis.bar(item_names, quantities)
        popular_axis.set_title("Most Ordered Food Items")
        popular_axis.set_xlabel("Food Item")
        popular_axis.set_ylabel("Quantity Ordered")
        popular_axis.tick_params(axis="x", rotation=25)
        popular_figure.tight_layout()

        popular_canvas = FigureCanvasTkAgg(
            popular_figure, master=popular_frame
        )
        popular_canvas.draw()
        popular_canvas.get_tk_widget().pack(fill="both", expand=True)
    else:
        tk.Label(
            popular_frame,
            text="No food-item data yet. This chart will appear after orders are placed.",
            bg="white", font=("Arial", 11)
        ).pack(pady=35)

    tk.Button(
        window, text="Close",
        command=window.destroy,
        bg=DARK, fg="white", relief="flat",
        font=("Arial", 11, "bold"), padx=20, pady=7
    ).pack(pady=10)


# ==================================================
# ADMIN DASHBOARD
# ==================================================

def show_admin_dashboard():
    clear_window()

    header = tk.Frame(root, bg=DARK, height=75)
    header.pack(fill="x")
    header.pack_propagate(False)

    tk.Label(
        header, text="FoodieHub Admin Dashboard",
        font=("Arial", 22, "bold"),
        bg=DARK, fg="white"
    ).pack(side="left", padx=20, pady=18)

    tk.Button(
        header, text="Logout",
        bg=ORANGE, fg="white",
        relief="flat", command=show_login
    ).pack(side="right", padx=20)

    con = get_connection()
    cur = con.cursor()

    customer_count = cur.execute(
        "SELECT COUNT(*) FROM customers"
    ).fetchone()[0]

    order_count = cur.execute(
        "SELECT COUNT(*) FROM orders"
    ).fetchone()[0]

    revenue = cur.execute(
        "SELECT COALESCE(SUM(total), 0) FROM orders"
    ).fetchone()[0]

    pending_count = cur.execute(""" SELECT COUNT(*) FROM orders WHERE status NOT IN ('Delivered', 'Cancelled') """).fetchone()[0]

    con.close()

    tk.Label(
        root, text="Dashboard Overview",
        font=("Arial", 22, "bold"), bg=BG
    ).pack(pady=20)

    stats = tk.Frame(root, bg=BG)
    stats.pack(fill="x", padx=20)

    stat_values = [
        ("Total Customers", customer_count),
        ("Total Orders", order_count),
        ("Total Revenue", "₹" + str(round(revenue, 2))),
        ("Active Orders", pending_count)
    ]

    for title, value in stat_values:
        card = tk.Frame(stats, bg="white", padx=15, pady=18)
        card.pack(side="left", expand=True, fill="x", padx=6)

        tk.Label(
            card, text=title,
            font=("Arial", 10), bg="white"
        ).pack()

        tk.Label(
            card, text=str(value),
            font=("Arial", 20, "bold"),
            fg=ORANGE, bg="white"
        ).pack(pady=8)

    buttons = tk.Frame(root, bg=BG)
    buttons.pack(pady=25)

    button_specs = [
        ("Manage Orders", show_admin_orders, 0, 0),
        ("View Customers", show_admin_customers, 0, 1),
        ("Manage Restaurants", show_manage_restaurants, 1, 0),
        ("Manage Menu Items", show_manage_menu_items, 1, 1),
        ("Sales Analytics", show_sales_analytics, 2, 0),
        ("View Customer Reviews", show_admin_reviews, 2, 1),
        ("Refresh Dashboard", show_admin_dashboard, 3, 0)
    ]

    for label, command, row, column in button_specs:
        tk.Button(
            buttons, text=label,
            font=("Arial", 12, "bold"),
            bg=ORANGE if label != "Refresh Dashboard" else DARK,
            fg="white", relief="flat", width=22,
            command=command
        ).grid(row=row, column=column, padx=10, pady=9, ipady=9)


# ==================================================
# ADMIN ORDER MANAGEMENT
# ==================================================

def show_admin_orders():
    window = tk.Toplevel(root)
    window.title("Admin - Manage Orders")
    window.geometry("950x600")
    window.configure(bg=BG)

    tk.Label(
        window, text="Manage Customer Orders",
        font=("Arial", 22, "bold"), bg=BG
    ).pack(pady=15)

    columns = ("ID", "Customer", "Total", "Status", "Payment", "Date")
    tree = ttk.Treeview(
        window, columns=columns, show="headings", height=14
    )

    for col in columns:
        tree.heading(col, text=col)
        tree.column(col, width=135, anchor="center")

    tree.pack(fill="both", expand=True, padx=15, pady=10)

    def load_orders():
        tree.delete(*tree.get_children())
        con = get_connection()
        rows = con.execute(""" SELECT orders.id, customers.name, orders.total, orders.status, COALESCE(orders.payment_method, 'Cash on Delivery'), orders.order_date FROM orders JOIN customers ON orders.customer_id = customers.id ORDER BY orders.id DESC """).fetchall()
        con.close()

        for row in rows:
            tree.insert("", "end", values=row)

    load_orders()

    controls = tk.Frame(window, bg=BG)
    controls.pack(pady=15)

    tk.Label(
        controls, text="New Order Status:",
        font=("Arial", 11, "bold"), bg=BG
    ).pack(side="left", padx=5)

    status_var = tk.StringVar(value="Preparing")
    status_box = ttk.Combobox(
        controls, textvariable=status_var,
        values=[
            "Order Placed", "Preparing", "Ready for Pickup",
            "Out for Delivery", "Delivered", "Cancelled"
        ],
        state="readonly", width=20
    )
    status_box.pack(side="left", padx=5)

    def update_status():
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("Select Order", "Select an order first.")
            return

        order_id = tree.item(selected[0])["values"][0]
        con = get_connection()
        con.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (status_var.get(), order_id)
        )
        con.commit()
        con.close()

        messagebox.showinfo("Updated", "Order status updated successfully.")
        load_orders()

    tk.Button(
        controls, text="Update Status",
        bg=ORANGE, fg="white", relief="flat",
        command=update_status
    ).pack(side="left", padx=10, ipadx=10, ipady=5)

    def view_selected_items():
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("Select Order", "Select an order first.")
            return
        order_id = tree.item(selected[0])["values"][0]
        show_order_items(order_id)

    tk.Button(
        controls, text="View Order Items",
        bg=DARK, fg="white", relief="flat",
        command=view_selected_items
    ).pack(side="left", padx=5, ipadx=10, ipady=5)


# ==================================================
# ADMIN: CUSTOMER REVIEWS
# ==================================================

def show_admin_reviews():
    window = tk.Toplevel(root)
    window.title("Customer Reviews")
    window.geometry("900x550")
    window.configure(bg=BG)

    tk.Label(window, text="Customer Reviews", font=("Arial", 22, "bold"),
             bg=BG, fg=ORANGE).pack(pady=15)
    columns = ("Order", "Customer", "Restaurant", "Rating", "Review", "Date")
    tree = ttk.Treeview(window, columns=columns, show="headings")
    for col, width in zip(columns, (70, 130, 140, 70, 330, 140)):
        tree.heading(col, text=col)
        tree.column(col, width=width, anchor="center")
    tree.pack(fill="both", expand=True, padx=15, pady=10)

    con = get_connection()
    rows = con.execute("""SELECT r.order_id, c.name, r.restaurant, r.rating, r.comment, r.review_date FROM reviews r JOIN customers c ON c.id=r.customer_id ORDER BY r.id DESC""").fetchall()
    con.close()
    for row in rows:
        tree.insert("", "end", values=row)
    tk.Button(window, text="Close", command=window.destroy, bg=DARK,
              fg="white", relief="flat").pack(pady=8)


# ==================================================
# ADMIN CUSTOMER MANAGEMENT
# ==================================================

def show_admin_customers():
    window = tk.Toplevel(root)
    window.title("Registered Customers")
    window.geometry("850x500")
    window.configure(bg=BG)

    tk.Label(
        window, text="Registered Customers",
        font=("Arial", 22, "bold"), bg=BG
    ).pack(pady=20)

    columns = ("ID", "Name", "Email", "Phone")
    tree = ttk.Treeview(
        window, columns=columns, show="headings", height=15
    )

    for col in columns:
        tree.heading(col, text=col)
        tree.column(col, width=190, anchor="center")

    tree.pack(fill="both", expand=True, padx=20, pady=10)

    con = get_connection()
    rows = con.execute(""" SELECT id, name, email, phone FROM customers ORDER BY id DESC """).fetchall()
    con.close()

    for row in rows:
        tree.insert("", "end", values=row)


# ==================================================
# STAGE 5: RESTAURANT MANAGEMENT
# ==================================================

def show_manage_restaurants():
    window = tk.Toplevel(root)
    window.title("Manage Restaurants")
    window.geometry("1050x600")
    window.configure(bg=BG)

    tk.Label(
        window, text="Restaurant Management",
        font=("Arial", 22, "bold"), bg=BG
    ).pack(pady=15)

    columns = ("ID", "Name", "Category", "Rating", "Delivery Time", "Image")
    tree = ttk.Treeview(
        window, columns=columns, show="headings", height=13
    )

    widths = (55, 170, 210, 75, 120, 130)
    for col, width in zip(columns, widths):
        tree.heading(col, text=col)
        tree.column(col, width=width, anchor="center")

    tree.pack(fill="both", expand=True, padx=15, pady=8)

    def load_restaurant_rows():
        tree.delete(*tree.get_children())
        con = get_connection()
        rows = con.execute(""" SELECT id, name, category, rating, delivery_time, image FROM restaurants ORDER BY id """).fetchall()
        con.close()
        for row in rows:
            tree.insert("", "end", values=row)

    def selected_restaurant():
        selected = tree.selection()
        if not selected:
            messagebox.showwarning(
                "Select Restaurant", "Select a restaurant first."
            )
            return None
        return tree.item(selected[0])["values"]

    def restaurant_form(title, existing=None):
        form = tk.Toplevel(window)
        form.title(title)
        # Extra height keeps all five fields and the Save button visible.
        form.geometry("500x620")
        form.minsize(460, 580)
        form.configure(bg=BG)
        form.transient(window)
        form.grab_set()

        labels = [
            ("Restaurant Name", "name"),
            ("Category", "category"),
            ("Rating", "rating"),
            ("Delivery Time", "delivery_time"),
            ("Image Filename", "image")
        ]
        entries = {}

        tk.Label(
            form, text=title, font=("Arial", 18, "bold"),
            bg=BG, fg=ORANGE
        ).pack(pady=15)

        panel = tk.Frame(form, bg="white", padx=20, pady=15)
        panel.pack(padx=20, fill="x")

        for label, key in labels:
            tk.Label(
                panel, text=label, bg="white",
                font=("Arial", 10, "bold")
            ).pack(anchor="w", pady=(5, 2))

            entry = tk.Entry(panel, width=38, font=("Arial", 10))
            entry.pack(ipady=4, pady=(0, 5))
            entries[key] = entry

            if existing:
                entry.insert(0, existing[{
                    "name": 1,
                    "category": 2,
                    "rating": 3,
                    "delivery_time": 4,
                    "image": 5
                }[key]])

        tk.Label(
            form,
            text="For images, enter a filename from Images/restaurants.",
            bg=BG, fg="#555555", wraplength=380
        ).pack(pady=8)

        def save():
            values = {key: entry.get().strip() for key, entry in entries.items()}
            if not all(values.values()):
                messagebox.showwarning(
                    "Missing Details", "Please fill in every field.", parent=form
                )
                return

            con = get_connection()
            try:
                if existing:
                    con.execute(""" UPDATE restaurants SET name=?, category=?, rating=?, delivery_time=?, image=? WHERE id=? """, (
                        values["name"], values["category"], values["rating"],
                        values["delivery_time"], values["image"], existing[0]
                    ))
                else:
                    con.execute(""" INSERT INTO restaurants (name, category, rating, delivery_time, image) VALUES (?, ?, ?, ?, ?) """, (
                        values["name"], values["category"], values["rating"],
                        values["delivery_time"], values["image"]
                    ))
                con.commit()
                form.destroy()
                load_restaurant_rows()
                messagebox.showinfo(
                    "Saved", "Restaurant details saved successfully.",
                    parent=window
                )
            except sqlite3.IntegrityError:
                messagebox.showerror(
                    "Duplicate Name",
                    "A restaurant with this name already exists.",
                    parent=form
                )
            finally:
                con.close()

        save_button = tk.Button(
            form, text="Save Restaurant",
            bg=ORANGE, fg="white", relief="flat",
            command=save
        )
        save_button.pack(pady=12, ipadx=18, ipady=7)

        # Pressing Enter in any field also saves the restaurant.
        form.bind("<Return>", lambda event: save())

    def add_restaurant():
        restaurant_form("Add Restaurant")

    def edit_restaurant():
        row = selected_restaurant()
        if row:
            restaurant_form("Edit Restaurant", row)

    def delete_restaurant():
        row = selected_restaurant()
        if not row:
            return

        if not messagebox.askyesno(
            "Confirm Delete",
            "Delete " + str(row[1]) + " and all its menu items?\n"
            "Existing order records will remain unchanged.",
            parent=window
        ):
            return

        con = get_connection()
        try:
            con.execute(
                "DELETE FROM menu_items WHERE restaurant_id = ?", (row[0],)
            )
            con.execute("DELETE FROM restaurants WHERE id = ?", (row[0],))
            con.commit()
            load_restaurant_rows()
            messagebox.showinfo(
                "Deleted", "Restaurant deleted successfully.", parent=window
            )
        finally:
            con.close()

    controls = tk.Frame(window, bg=BG)
    controls.pack(pady=12)

    tk.Button(
        controls, text="Add Restaurant", bg=ORANGE, fg="white",
        relief="flat", command=add_restaurant
    ).pack(side="left", padx=6, ipadx=10, ipady=7)

    tk.Button(
        controls, text="Edit Selected", bg=DARK, fg="white",
        relief="flat", command=edit_restaurant
    ).pack(side="left", padx=6, ipadx=10, ipady=7)

    tk.Button(
        controls, text="Delete Selected", bg="#b83227", fg="white",
        relief="flat", command=delete_restaurant
    ).pack(side="left", padx=6, ipadx=10, ipady=7)

    tk.Button(
        controls, text="Refresh", bg="#555555", fg="white",
        relief="flat", command=load_restaurant_rows
    ).pack(side="left", padx=6, ipadx=10, ipady=7)

    load_restaurant_rows()


# ==================================================
# STAGE 5: MENU ITEM MANAGEMENT
# ==================================================

def show_manage_menu_items():
    window = tk.Toplevel(root)
    window.title("Manage Menu Items")
    window.geometry("850x600")
    window.configure(bg=BG)

    tk.Label(
        window, text="Food Menu Management",
        font=("Arial", 22, "bold"), bg=BG
    ).pack(pady=15)

    filter_frame = tk.Frame(window, bg=BG)
    filter_frame.pack(pady=5)

    tk.Label(
        filter_frame, text="Restaurant:", bg=BG,
        font=("Arial", 11, "bold")
    ).pack(side="left", padx=5)

    restaurant_var = tk.StringVar()
    restaurant_box = ttk.Combobox(
        filter_frame, textvariable=restaurant_var,
        state="readonly", width=32
    )
    restaurant_box.pack(side="left", padx=5)

    columns = ("ID", "Food Item", "Price (₹)")
    tree = ttk.Treeview(
        window, columns=columns, show="headings", height=15
    )

    tree.heading("ID", text="ID")
    tree.heading("Food Item", text="Food Item")
    tree.heading("Price (₹)", text="Price (₹)")
    tree.column("ID", width=70, anchor="center")
    tree.column("Food Item", width=430, anchor="w")
    tree.column("Price (₹)", width=150, anchor="center")
    tree.pack(fill="both", expand=True, padx=20, pady=10)

    restaurant_map = {}

    def refresh_restaurant_choices():
        con = get_connection()
        rows = con.execute(
            "SELECT id, name FROM restaurants ORDER BY name"
        ).fetchall()
        con.close()

        restaurant_map.clear()
        for restaurant_id, name in rows:
            restaurant_map[name] = restaurant_id

        names = list(restaurant_map.keys())
        restaurant_box["values"] = names

        if names:
            if restaurant_var.get() not in names:
                restaurant_var.set(names[0])
        else:
            restaurant_var.set("")

        load_menu_rows()

    def load_menu_rows():
        tree.delete(*tree.get_children())
        restaurant_name = restaurant_var.get()
        restaurant_id = restaurant_map.get(restaurant_name)

        if restaurant_id is None:
            return

        con = get_connection()
        rows = con.execute(""" SELECT id, name, price FROM menu_items WHERE restaurant_id = ? ORDER BY id """, (restaurant_id,)).fetchall()
        con.close()

        for row in rows:
            tree.insert("", "end", values=row)

    def selected_menu_item():
        selected = tree.selection()
        if not selected:
            messagebox.showwarning(
                "Select Item", "Select a menu item first."
            )
            return None
        return tree.item(selected[0])["values"]

    def menu_item_form(title, existing=None):
        restaurant_name = restaurant_var.get()
        restaurant_id = restaurant_map.get(restaurant_name)

        if restaurant_id is None:
            messagebox.showwarning(
                "No Restaurant", "Add a restaurant before adding menu items.",
                parent=window
            )
            return

        form = tk.Toplevel(window)
        form.title(title)
        form.geometry("450x380")
        form.minsize(420, 350)
        form.configure(bg=BG)
        form.transient(window)
        form.grab_set()

        tk.Label(
            form, text=title, font=("Arial", 18, "bold"),
            bg=BG, fg=ORANGE
        ).pack(pady=15)

        panel = tk.Frame(form, bg="white", padx=20, pady=15)
        panel.pack(padx=20, fill="x")

        tk.Label(
            panel, text="Restaurant", bg="white",
            font=("Arial", 10, "bold")
        ).pack(anchor="w")
        tk.Label(
            panel, text=restaurant_name, bg="white",
            font=("Arial", 11)
        ).pack(anchor="w", pady=(2, 8))

        tk.Label(
            panel, text="Food Item Name", bg="white",
            font=("Arial", 10, "bold")
        ).pack(anchor="w")
        name_entry = tk.Entry(panel, width=35, font=("Arial", 11))
        name_entry.pack(ipady=4, pady=(2, 8))

        tk.Label(
            panel, text="Price (₹)", bg="white",
            font=("Arial", 10, "bold")
        ).pack(anchor="w")
        price_entry = tk.Entry(panel, width=35, font=("Arial", 11))
        price_entry.pack(ipady=4, pady=(2, 5))

        if existing:
            name_entry.insert(0, existing[1])
            price_entry.insert(0, str(existing[2]))

        def save():
            item_name = name_entry.get().strip()
            price_text = price_entry.get().strip()

            if not item_name or not price_text:
                messagebox.showwarning(
                    "Missing Details", "Enter item name and price.",
                    parent=form
                )
                return

            try:
                price = float(price_text)
                if price < 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning(
                    "Invalid Price", "Enter a valid non-negative price.",
                    parent=form
                )
                return

            con = get_connection()
            try:
                if existing:
                    con.execute(""" UPDATE menu_items SET name = ?, price = ? WHERE id = ? AND restaurant_id = ? """, (item_name, price, existing[0], restaurant_id))
                else:
                    con.execute(""" INSERT INTO menu_items (restaurant_id, name, price) VALUES (?, ?, ?) """, (restaurant_id, item_name, price))

                con.commit()
                form.destroy()
                load_menu_rows()
                messagebox.showinfo(
                    "Saved", "Menu item saved successfully.", parent=window
                )
            finally:
                con.close()

        tk.Button(
            form, text="Save Menu Item",
            bg=ORANGE, fg="white", relief="flat",
            command=save
        ).pack(pady=12, ipadx=18, ipady=7)

        # Pressing Enter in either field also saves the menu item.
        form.bind("<Return>", lambda event: save())

    def add_item():
        menu_item_form("Add Food Item")

    def edit_item():
        row = selected_menu_item()
        if row:
            menu_item_form("Edit Food Item", row)

    def delete_item():
        row = selected_menu_item()
        if not row:
            return

        if not messagebox.askyesno(
            "Confirm Delete",
            "Delete '" + str(row[1]) + "' from this menu?",
            parent=window
        ):
            return

        con = get_connection()
        con.execute("DELETE FROM menu_items WHERE id = ?", (row[0],))
        con.commit()
        con.close()
        load_menu_rows()
        messagebox.showinfo(
            "Deleted", "Menu item deleted successfully.", parent=window
        )

    restaurant_box.bind(
        "<<ComboboxSelected>>", lambda event: load_menu_rows()
    )

    controls = tk.Frame(window, bg=BG)
    controls.pack(pady=12)

    tk.Button(
        controls, text="Add Food Item", bg=ORANGE, fg="white",
        relief="flat", command=add_item
    ).pack(side="left", padx=6, ipadx=10, ipady=7)

    tk.Button(
        controls, text="Edit Selected", bg=DARK, fg="white",
        relief="flat", command=edit_item
    ).pack(side="left", padx=6, ipadx=10, ipady=7)

    tk.Button(
        controls, text="Delete Selected", bg="#b83227", fg="white",
        relief="flat", command=delete_item
    ).pack(side="left", padx=6, ipadx=10, ipady=7)

    tk.Button(
        controls, text="Refresh", bg="#555555", fg="white",
        relief="flat", command=refresh_restaurant_choices
    ).pack(side="left", padx=6, ipadx=10, ipady=7)

    refresh_restaurant_choices()


# ==================================================
# IMAGE LOADING
# ==================================================

def load_restaurant_image(filename, size=(300, 140)):
    path = os.path.join(IMAGE_FOLDER, filename)

    try:
        image = Image.open(path).convert("RGB")
        image = ImageOps.fit(
            image, size, method=Image.Resampling.LANCZOS
        )
        return ImageTk.PhotoImage(image)

    except Exception as error:
        print("Image error:", path, error)
        return None


# ==================================================
# CART
# ==================================================

def add_to_cart(restaurant_name, item):
    key = (restaurant_name, item["name"])

    if key in cart:
        cart[key]["quantity"] += 1
        # Keep the cart price aligned with the menu price at add time.
    else:
        cart[key] = {
            "restaurant": restaurant_name,
            "name": item["name"],
            "price": item["price"],
            "quantity": 1
        }

    messagebox.showinfo(
        "FoodieHub", item["name"] + " added to cart!"
    )


def calculate_total():
    return sum(
        item["price"] * item["quantity"]
        for item in cart.values()
    )


def change_quantity(key, amount, window):
    if key in cart:
        cart[key]["quantity"] += amount
        if cart[key]["quantity"] <= 0:
            del cart[key]

    window.destroy()
    open_cart()


def open_cart():
    window = tk.Toplevel(root)
    window.title("My Cart")
    window.geometry("600x550")
    window.configure(bg=BG)

    tk.Label(
        window, text="My Shopping Cart",
        font=("Arial", 22, "bold"), bg=BG
    ).pack(pady=20)

    content = tk.Frame(window, bg=BG)
    content.pack(fill="both", expand=True, padx=20)

    if not cart:
        tk.Label(
            content, text="Your cart is empty!",
            font=("Arial", 15), bg=BG
        ).pack(pady=35)

    for key, item in list(cart.items()):
        row = tk.Frame(content, bg="white", padx=10, pady=12)
        row.pack(fill="x", pady=5)

        tk.Label(
            row, text=item["name"] + "\n" + item["restaurant"],
            font=("Arial", 11, "bold"), bg="white", justify="left"
        ).pack(side="left")

        controls = tk.Frame(row, bg="white")
        controls.pack(side="right")

        tk.Button(
            controls, text="-",
            command=lambda k=key: change_quantity(k, -1, window)
        ).pack(side="left")

        tk.Label(
            controls, text=str(item["quantity"]), bg="white"
        ).pack(side="left", padx=5)

        tk.Button(
            controls, text="+",
            command=lambda k=key: change_quantity(k, 1, window)
        ).pack(side="left")

        tk.Label(
            row,
            text="₹" + str(item["price"] * item["quantity"]),
            font=("Arial", 11, "bold"), bg="white"
        ).pack(side="right", padx=12)

    tk.Label(
        window, text="Total: ₹" + str(calculate_total()),
        font=("Arial", 18, "bold"), bg=BG, fg=ORANGE
    ).pack(pady=15)

    tk.Button(
        window, text="Proceed to Checkout",
        bg=ORANGE, fg="white", relief="flat",
        command=lambda: checkout(window)
    ).pack(pady=10, ipadx=15, ipady=8)


# ==================================================
# CHECKOUT
# ==================================================

def checkout(cart_window):
    if not cart:
        messagebox.showwarning("Empty Cart", "Add items first.")
        return

    window = tk.Toplevel(root)
    window.title("Checkout")
    window.geometry("500x610")
    window.configure(bg=BG)

    tk.Label(window, text="Delivery & Payment", font=("Arial", 22, "bold"),
             bg=BG, fg=ORANGE).pack(pady=18)
    tk.Label(window, text="Customer: " + current_user["name"],
             font=("Arial", 12), bg=BG).pack(pady=4)
    tk.Label(window, text="Delivery Address", font=("Arial", 11, "bold"),
             bg=BG).pack(pady=(12, 5))
    address_entry = tk.Text(window, width=42, height=4)
    address_entry.pack()

    tk.Label(window, text="Choose Payment Method", font=("Arial", 11, "bold"),
             bg=BG).pack(pady=(15, 5))
    payment_var = tk.StringVar(value="Cash on Delivery")
    payment_box = ttk.Combobox(window, textvariable=payment_var, state="readonly",
        values=["Credit/Debit Card", "UPI", "Cash on Delivery"], width=28)
    payment_box.pack(pady=5)
    payment_note = tk.Label(window,
        text="Demo checkout: no real payment is collected or processed.",
        bg=BG, fg="#555555", wraplength=420)
    payment_note.pack(pady=5)

    def update_payment_note(event=None):
        method = payment_var.get()
        if method == "UPI":
            payment_note.config(text="UPI selected. This demo records the method only; it does not connect to a UPI app or process payment.")
        elif method == "Credit/Debit Card":
            payment_note.config(text="Card selected. Do not enter card details: this demo does not process real card payments.")
        else:
            payment_note.config(text="Pay the delivery amount to the delivery person when your order arrives.")
    payment_box.bind("<<ComboboxSelected>>", update_payment_note)

    tk.Label(window, text="Total: ₹" + str(calculate_total()),
             font=("Arial", 18, "bold"), bg=BG, fg=ORANGE).pack(pady=15)

    def place_order():
        address = address_entry.get("1.0", "end").strip()
        if not address:
            messagebox.showwarning("Missing Address", "Enter your delivery address.", parent=window)
            return
        method = payment_var.get()
        payment_status = "Pending" if method == "Cash on Delivery" else "Demo - Not Processed"
        con = get_connection()
        cur = con.cursor()
        try:
            cur.execute("""INSERT INTO orders (customer_id, address, total, status, order_date, payment_method, payment_status) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (current_user["id"], address, calculate_total(), "Order Placed",
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"), method, payment_status))
            order_id = cur.lastrowid
            for item in cart.values():
                cur.execute("""INSERT INTO order_items (order_id, restaurant, item_name, price, quantity) VALUES (?, ?, ?, ?, ?)""",
                    (order_id, item["restaurant"], item["name"], item["price"], item["quantity"]))
            con.commit()
            cart.clear()
            window.destroy()
            cart_window.destroy()
            messagebox.showinfo("Order Placed",
                "Order saved successfully!\nOrder ID: " + str(order_id) +
                "\nPayment: " + method + "\nStatus: Order Placed\n\nNote: Online payment is demo-only; no money was charged.")
        except sqlite3.Error as error:
            con.rollback()
            messagebox.showerror("Database Error", str(error), parent=window)
        finally:
            con.close()

    tk.Button(window, text="Place Order", bg=ORANGE, fg="white",
              relief="flat", command=place_order).pack(pady=12, ipadx=20, ipady=8)


# ==================================================
# ORDER HISTORY
# ==================================================

def show_order_history():
    window = tk.Toplevel(root)
    window.title("My Orders - Tracking")
    window.geometry("760x650")
    window.configure(bg=BG)

    tk.Label(window, text="My Orders & Live Status", font=("Arial", 22, "bold"),
             bg=BG, fg=ORANGE).pack(pady=18)
    con = get_connection()
    orders = con.execute("""SELECT id, total, status, order_date, address, COALESCE(payment_method, 'Cash on Delivery'), COALESCE(payment_status, 'Pending') FROM orders WHERE customer_id=? ORDER BY id DESC""", (current_user["id"],)).fetchall()
    con.close()

    if not orders:
        tk.Label(window, text="No previous orders found.", font=("Arial", 14), bg=BG).pack(pady=30)
        return

    canvas = tk.Canvas(window, bg=BG, highlightthickness=0)
    scrollbar = ttk.Scrollbar(window, orient="vertical", command=canvas.yview)
    content = tk.Frame(canvas, bg=BG)
    content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=content, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True, padx=10, pady=5)

    for order in orders:
        order_id, total, status, order_date, address, method, pay_status = order
        card = tk.Frame(content, bg="white", padx=14, pady=12)
        card.pack(fill="x", padx=12, pady=7)
        details = (f"Order ID: {order_id} | Total: ₹{total}\n"
                   f"Order status: {status}\n"
                   f"Payment: {method} ({pay_status})\n"
                   f"Date: {order_date}\nDelivery address: {address}")
        tk.Label(card, text=details, font=("Arial", 10), bg="white", justify="left").pack(anchor="w")
        actions = tk.Frame(card, bg="white")
        actions.pack(fill="x", pady=(8, 0))
        tk.Button(actions, text="Track Order", bg=ORANGE, fg="white", relief="flat",
                  command=lambda oid=order_id: show_order_tracking(oid)).pack(side="left", padx=4)
        tk.Button(actions, text="View Items", bg=DARK, fg="white", relief="flat",
                  command=lambda oid=order_id: show_order_items(oid)).pack(side="left", padx=4)
        if status == "Delivered":
            tk.Button(actions, text="Write / Edit Review", bg="#287a45", fg="white", relief="flat",
                      command=lambda oid=order_id: write_review(oid)).pack(side="left", padx=4)


def show_order_tracking(order_id):
    con = get_connection()
    row = con.execute("SELECT status, order_date FROM orders WHERE id=? AND customer_id=?",
                      (order_id, current_user["id"])).fetchone()
    con.close()
    if not row:
        messagebox.showerror("Not Found", "Order could not be found.")
        return
    status, order_date = row
    stages = ["Order Placed", "Preparing", "Ready for Pickup", "Out for Delivery", "Delivered"]
    win = tk.Toplevel(root)
    win.title("Track Order #" + str(order_id))
    win.geometry("480x400")
    win.configure(bg=BG)
    tk.Label(win, text="Track Order #" + str(order_id), font=("Arial", 20, "bold"),
             bg=BG, fg=ORANGE).pack(pady=18)
    tk.Label(win, text="Placed: " + order_date, bg=BG).pack(pady=5)
    if status == "Cancelled":
        tk.Label(win, text="✖ This order has been cancelled.", fg="red", bg=BG,
                 font=("Arial", 13, "bold")).pack(pady=25)
    else:
        current_index = stages.index(status) if status in stages else 0
        for index, stage in enumerate(stages):
            mark = "✓" if index <= current_index else "○"
            color = "#238636" if index <= current_index else "#777777"
            tk.Label(win, text=f"{mark} {stage}", font=("Arial", 13, "bold"),
                     fg=color, bg=BG).pack(anchor="w", padx=100, pady=8)
    tk.Label(win, text="Tracking updates when the restaurant/admin changes the order status.",
             bg=BG, fg="#555555", wraplength=420).pack(pady=15)


def write_review(order_id):
    con = get_connection()
    order = con.execute("SELECT status FROM orders WHERE id=? AND customer_id=?",
                         (order_id, current_user["id"])).fetchone()
    existing = con.execute("SELECT rating, comment FROM reviews WHERE order_id=? AND customer_id=?",
                           (order_id, current_user["id"])).fetchone()
    con.close()
    if not order or order[0] != "Delivered":
        messagebox.showwarning("Not Delivered", "You can review an order after it is delivered.")
        return

    win = tk.Toplevel(root)
    win.title("Rate Your Order")
    win.geometry("440x420")
    win.configure(bg=BG)
    tk.Label(win, text="Rate Your Experience", font=("Arial", 20, "bold"),
             bg=BG, fg=ORANGE).pack(pady=18)
    rating_var = tk.IntVar(value=existing[0] if existing else 5)
    tk.Label(win, text="Your rating (1 to 5 stars)", bg=BG).pack(pady=5)
    ttk.Combobox(win, textvariable=rating_var, values=[1, 2, 3, 4, 5],
                 state="readonly", width=8).pack(pady=5)
    tk.Label(win, text="Your review", bg=BG).pack(pady=(15, 5))
    comment = tk.Text(win, width=42, height=7)
    comment.pack(padx=12)
    if existing and existing[1]:
        comment.insert("1.0", existing[1])

    def save_review():
        rating = int(rating_var.get())
        text_value = comment.get("1.0", "end").strip()
        con = get_connection()
        try:
            restaurant_row = con.execute("SELECT restaurant FROM order_items WHERE order_id=? LIMIT 1",
                                         (order_id,)).fetchone()
            restaurant_name = restaurant_row[0] if restaurant_row else "FoodieHub"
            con.execute("""INSERT INTO reviews(order_id, customer_id, restaurant, rating, comment, review_date) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(order_id) DO UPDATE SET rating=excluded.rating, comment=excluded.comment, review_date=excluded.review_date""",
                (order_id, current_user["id"], restaurant_name, rating, text_value,
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            con.commit()
            messagebox.showinfo("Review Saved", "Thank you! Your review has been saved.", parent=win)
            win.destroy()
        except sqlite3.Error as error:
            messagebox.showerror("Database Error", str(error), parent=win)
        finally:
            con.close()
    tk.Button(win, text="Submit Review", command=save_review, bg=ORANGE,
              fg="white", relief="flat").pack(pady=14, ipadx=15, ipady=6)


def show_order_items(order_id):
    window = tk.Toplevel(root)
    window.title("Order Items")
    window.geometry("450x400")
    window.configure(bg=BG)

    tk.Label(
        window, text="Order Items",
        font=("Arial", 20, "bold"), bg=BG
    ).pack(pady=20)

    con = get_connection()
    items = con.execute(""" SELECT restaurant, item_name, price, quantity FROM order_items WHERE order_id = ? """, (order_id,)).fetchall()
    con.close()

    for restaurant, name, price, quantity in items:
        tk.Label(
            window,
            text=(
                restaurant + " - " + name
                + "\n₹" + str(price) + " x " + str(quantity)
            ),
            font=("Arial", 12), bg="white",
            padx=15, pady=10
        ).pack(fill="x", padx=20, pady=5)


# ==================================================
# RESTAURANT MENU
# ==================================================

def open_menu(restaurant):
    window = tk.Toplevel(root)
    window.title(restaurant["name"] + " Menu")
    window.geometry("650x650")
    window.configure(bg=BG)

    tk.Label(
        window, text=restaurant["name"],
        font=("Arial", 24, "bold"), fg=ORANGE, bg=BG
    ).pack(pady=20)

    tk.Button(
        window, text="View Cart",
        bg=ORANGE, fg="white", relief="flat",
        command=open_cart
    ).pack(pady=8)

    if not restaurant["menu"]:
        tk.Label(
            window, text="No food items available yet.",
            font=("Arial", 13), bg=BG
        ).pack(pady=20)

    for item in restaurant["menu"]:
        card = tk.Frame(window, bg="white", padx=15, pady=12)
        card.pack(fill="x", padx=20, pady=6)

        tk.Label(
            card, text=item["name"],
            font=("Arial", 13, "bold"), bg="white"
        ).pack(side="left")

        tk.Label(
            card, text="₹" + str(item["price"]), bg="white"
        ).pack(side="left", padx=20)

        tk.Button(
            card, text="Add +",
            bg=ORANGE, fg="white", relief="flat",
            command=lambda i=item, r=restaurant["name"]:
                add_to_cart(r, i)
        ).pack(side="right")


# ==================================================
# CUSTOMER HOME PAGE
# ==================================================

def show_home():
    clear_window()
    restaurant_images.clear()

    header = tk.Frame(root, bg=ORANGE, height=75)
    header.pack(fill="x")
    header.pack_propagate(False)

    tk.Label(
        header, text="FoodieHub",
        font=("Arial", 25, "bold"), bg=ORANGE, fg="white"
    ).pack(side="left", padx=25, pady=15)

    tk.Label(
        header, text="Hello, " + current_user["name"],
        font=("Arial", 12, "bold"), bg=ORANGE, fg="white"
    ).pack(side="left", padx=10)

    tk.Button(
        header, text="Logout",
        command=logout, bg="white", fg=ORANGE, relief="flat"
    ).pack(side="right", padx=12)

    tk.Button(
        header, text="Order History",
        command=show_order_history, bg="white", fg=ORANGE,
        relief="flat"
    ).pack(side="right", padx=5)

    tk.Button(
        header, text="View Cart",
        command=open_cart, bg="white", fg=ORANGE,
        relief="flat"
    ).pack(side="right", padx=5)

    tk.Label(
        root, text="Discover Restaurants Near You",
        font=("Arial", 22, "bold"), bg=BG
    ).pack(pady=20)

    search_frame = tk.Frame(root, bg=BG)
    search_frame.pack(pady=5)

    search_entry = tk.Entry(search_frame, width=35, font=("Arial", 12))
    search_entry.pack(side="left", ipady=7, padx=5)

    # Scrollable area for restaurant cards.
    restaurant_area = tk.Frame(root, bg=BG)
    restaurant_area.pack(fill="both", expand=True, padx=15, pady=10)

    restaurant_canvas = tk.Canvas(
        restaurant_area, bg=BG, highlightthickness=0
    )
    restaurant_scrollbar = ttk.Scrollbar(
        restaurant_area, orient="vertical",
        command=restaurant_canvas.yview
    )
    restaurant_canvas.configure(
        yscrollcommand=restaurant_scrollbar.set
    )

    restaurant_scrollbar.pack(side="right", fill="y")
    restaurant_canvas.pack(side="left", fill="both", expand=True)

    cards_frame = tk.Frame(restaurant_canvas, bg=BG)
    cards_window = restaurant_canvas.create_window(
        (0, 0), window=cards_frame, anchor="nw"
    )

    def update_scroll_region(event=None):
        restaurant_canvas.configure(
            scrollregion=restaurant_canvas.bbox("all")
        )

    def resize_cards_frame(event):
        restaurant_canvas.itemconfigure(
            cards_window, width=event.width
        )

    cards_frame.bind("<Configure>", update_scroll_region)
    restaurant_canvas.bind("<Configure>", resize_cards_frame)

    def on_mousewheel(event):
        restaurant_canvas.yview_scroll(
            int(-1 * (event.delta / 120)), "units"
        )

    restaurant_canvas.bind_all("<MouseWheel>", on_mousewheel)

    def display_restaurants(search_text=""):
        for widget in cards_frame.winfo_children():
            widget.destroy()

        restaurant_images.clear()
        all_restaurants = get_restaurants()
        query = search_text.lower()

        filtered = [
            r for r in all_restaurants
            if query in r["name"].lower()
            or query in r["category"].lower()
        ]

        if not filtered:
            tk.Label(
                cards_frame, text="No restaurants found.",
                font=("Arial", 14), bg=BG
            ).pack(pady=30)
            return

        # Arrange restaurant cards in a 3-column grid.
        # Additional restaurants automatically continue on the next row.
        for column in range(3):
            cards_frame.grid_columnconfigure(column, weight=1)

        for index, restaurant in enumerate(filtered):
            card = tk.Frame(
                cards_frame, bg="white",
                padx=10, pady=10, bd=1, relief="solid"
            )
            card.grid(
                row=index // 3,
                column=index % 3,
                padx=8,
                pady=10,
                sticky="n"
            )

            photo = load_restaurant_image(restaurant["image"])

            if photo:
                restaurant_images.append(photo)
                tk.Label(card, image=photo, bg="white").pack()
            else:
                tk.Label(
                    card, text="Image unavailable",
                    bg="white", width=35, height=7
                ).pack()

            tk.Label(
                card, text=restaurant["name"],
                font=("Arial", 15, "bold"), bg="white"
            ).pack(anchor="w", pady=5)

            tk.Label(
                card, text=restaurant["category"],
                font=("Arial", 10), bg="white"
            ).pack(anchor="w")

            tk.Label(
                card,
                text="Rating: " + restaurant["rating"]
                + " | " + restaurant["time"],
                font=("Arial", 10), bg="white"
            ).pack(anchor="w", pady=7)

            tk.Button(
                card, text="View Menu",
                bg=ORANGE, fg="white", relief="flat",
                command=lambda r=restaurant: open_menu(r)
            ).pack(fill="x", pady=5)

    tk.Button(
        search_frame, text="Search",
        bg=ORANGE, fg="white", relief="flat",
        command=lambda: display_restaurants(search_entry.get().strip())
    ).pack(side="left", padx=5, ipady=5)

    display_restaurants()

    tk.Label(
        root, text="FoodieHub | Online Food Ordering System",
        bg=DARK, fg="white", pady=10
    ).pack(fill="x", side="bottom")


# ==================================================
# LOGOUT
# ==================================================

def logout():
    global current_user

    if cart and not messagebox.askyesno(
        "Logout", "Your cart will be cleared. Continue?"
    ):
        return

    cart.clear()
    current_user = None
    show_login()


# ==================================================
# START APPLICATION
# ==================================================

initialize_database()
show_login()

root.mainloop()