"""Knowledge Institute of Technology Library - Library Management System (Flask + SQLite)."""
import os
import re
import sqlite3
from datetime import date, timedelta
from functools import wraps

from flask import (Flask, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY","dev-only-secret") # change for real deployments
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db")

FINE_PER_DAY = 5      # Rs. per late day
DUE_SOON_DAYS = 3     # "due soon" window
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS books(id INTEGER PRIMARY KEY AUTOINCREMENT, book_id TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  author TEXT NOT NULL, category TEXT NOT NULL, isbn TEXT, quantity INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'Available');
CREATE TABLE IF NOT EXISTS students(id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  department TEXT NOT NULL, email TEXT NOT NULL, phone TEXT);
CREATE TABLE IF NOT EXISTS issued_books(id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL REFERENCES students(id),
  book_id INTEGER NOT NULL REFERENCES books(id), issue_date TEXT NOT NULL, due_date TEXT NOT NULL, return_date TEXT,
  status TEXT NOT NULL DEFAULT 'Issued', fine INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY AUTOINCREMENT, issue_id INTEGER NOT NULL REFERENCES issued_books(id),
  reminder_date TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Sent');
CREATE TABLE IF NOT EXISTS fines(id INTEGER PRIMARY KEY AUTOINCREMENT, issue_id INTEGER NOT NULL REFERENCES issued_books(id),
  amount INTEGER NOT NULL, payment_status TEXT NOT NULL DEFAULT 'Pending', payment_date TEXT);
"""

# One query reused everywhere: an issue with its student, book, reminder count and fine status.
BASE_SQL = """
SELECT i.*, s.name AS student_name, s.student_id AS sid, s.department, s.email,
       b.name AS book_name, b.book_id AS bid,
       (SELECT COUNT(*) FROM reminders r WHERE r.issue_id = i.id) AS reminder_count,
       f.payment_status AS fine_status, f.payment_date AS fine_paid_date
FROM issued_books i
JOIN students s ON s.id = i.student_id
JOIN books b ON b.id = i.book_id
LEFT JOIN fines f ON f.issue_id = i.id
"""


# ---------------------------------------------------------------- database helpers
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_=None):
    db = g.pop("db", None)
    if db:
        db.close()


def q(sql, args=(), one=False):
    """Run a SELECT. one=True returns a single row (or None)."""
    rows = get_db().execute(sql, args).fetchall()
    if one:
        return rows[0] if rows else None
    return rows


def run(sql, args=()):
    """Run INSERT/UPDATE/DELETE and commit."""
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur


def refresh_book(pk):
    """Set a book's status: 'Available' if any copy is free, otherwise 'Issued'."""
    book = q("SELECT quantity FROM books WHERE id=?", (pk,), one=True)
    out = q("SELECT COUNT(*) c FROM issued_books WHERE book_id=? AND status='Issued'", (pk,), one=True)["c"]
    run("UPDATE books SET status=? WHERE id=?",
        ("Available" if book["quantity"] - out > 0 else "Issued", pk))


def init_db():
    """Create tables and insert demo data on first run."""
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        d = lambda n: (date.today() + timedelta(days=n)).isoformat()
        db.execute("INSERT INTO users(username,password) VALUES(?,?)",
                   ("admin", generate_password_hash("admin123")))
        db.executemany("INSERT INTO books(book_id,name,author,category,isbn,quantity) VALUES(?,?,?,?,?,?)", [
            ("B001", "Python Programming", "Mark Lutz", "Programming", "9780596158101", 3),
            ("B002", "Data Science Fundamentals", "Joel Grus", "Data Science", "9781492041139", 2),
            ("B003", "Database Management Systems", "Raghu Ramakrishnan", "Database", "9780072465631", 2),
            ("B004", "Computer Networks", "Andrew Tanenbaum", "Networking", "9780132126953", 2),
            ("B005", "Artificial Intelligence", "Stuart Russell", "AI & ML", "9780136042594", 2),
            ("B006", "Web Development", "Jon Duckett", "Web", "9781118008188", 3),
            ("B007", "Machine Learning Basics", "Tom Mitchell", "AI & ML", "9780070428072", 2),
            ("B008", "Power BI Analytics", "Brett Powell", "Data Science", "9781788297233", 2)])
        db.executemany("INSERT INTO students(student_id,name,department,email,phone) VALUES(?,?,?,?,?)", [
            ("S001", "Laksshitha Sri", "CSE", "laksshitha@kit.edu", "9876543210"),
            ("S002", "Kavinaya", "IT", "kavinaya@kit.edu", "9876543211"),
            ("S003", "Manoj", "ECE", "manoj@kit.edu", "9876543212"),
            ("S004", "Priya", "CSE", "priya@kit.edu", "9876543213"),
            ("S005", "Rahul", "IT", "rahul@kit.edu", "9876543214")])
        # (student, book, issue, due, return, status, fine)
        db.executemany("INSERT INTO issued_books(student_id,book_id,issue_date,due_date,return_date,status,fine) VALUES(?,?,?,?,?,?,?)", [
            (5, 1, d(-12), d(2), None, "Issued", 0),     # due soon
            (4, 6, d(-14), d(0), None, "Issued", 0),     # due today
            (3, 4, d(-20), d(-5), None, "Issued", 0),    # overdue 5 days
            (2, 5, d(-25), d(-8), None, "Issued", 0),    # overdue 8 days
            (1, 3, d(-30), d(-16), d(-13), "Returned", 15),  # returned late, fine pending
            (5, 7, d(-40), d(-26), d(-22), "Returned", 20),  # returned late, fine paid
            (4, 2, d(-3), d(11), None, "Issued", 0)])    # normal
        db.executemany("INSERT INTO fines(issue_id,amount,payment_status,payment_date) VALUES(?,?,?,?)",
                       [(5, 15, "Pending", None), (6, 20, "Paid", d(-21))])
        db.execute("INSERT INTO reminders(issue_id,reminder_date,status) VALUES(4,?,'Sent')", (d(-1),))
        db.commit()
        for (pk,) in db.execute("SELECT id FROM books").fetchall():
            out = db.execute("SELECT COUNT(*) FROM issued_books WHERE book_id=? AND status='Issued'", (pk,)).fetchone()[0]
            qty = db.execute("SELECT quantity FROM books WHERE id=?", (pk,)).fetchone()[0]
            db.execute("UPDATE books SET status=? WHERE id=?", ("Available" if qty - out > 0 else "Issued", pk))
        db.commit()
    db.close()


# ---------------------------------------------------------------- logic helpers
def enrich(rows):
    """Add days_left, state (Overdue / Due Today / Due Soon / Issued / Returned), days_late and pending fine."""
    today, out = date.today(), []
    for r in rows:
        d = dict(r)
        due = date.fromisoformat(d["due_date"])
        d["days_left"] = (due - today).days
        if d["return_date"]:
            d["state"] = "Returned"
            d["days_late"] = max((date.fromisoformat(d["return_date"]) - due).days, 0)
            d["pending"] = d["fine"] if d["fine_status"] == "Pending" else 0
        else:
            d["days_late"] = max(-d["days_left"], 0)
            if d["days_left"] < 0:
                d["state"] = "Overdue"
            elif d["days_left"] == 0:
                d["state"] = "Due Today"
            elif d["days_left"] <= DUE_SOON_DAYS:
                d["state"] = "Due Soon"
            else:
                d["state"] = "Issued"
            d["pending"] = d["days_late"] * FINE_PER_DAY  # fine still growing
        out.append(d)
    return out


def deliver_reminder(issue):
    """Reminder delivery hook (simulated).
    To send real messages later, add email (smtplib) or SMS (Twilio etc.) code here
    using issue['email'], issue['student_name'], issue['book_name'] and issue['due_date']."""
    print(f"[REMINDER] To {issue['email']}: '{issue['book_name']}' is due on {issue['due_date']}.")
    return True


def check_book(f, pk=None):
    if not all(f[k] for k in ("book_id", "name", "author", "category", "quantity")):
        return "Please fill in Book ID, Name, Author, Category and Quantity."
    if not f["quantity"].isdigit() or int(f["quantity"]) < 1:
        return "Quantity must be a whole number of 1 or more."
    if q("SELECT id FROM books WHERE book_id=? AND id IS NOT ?", (f["book_id"], pk), one=True):
        return "Book ID already exists. Use a unique Book ID."
    if pk:
        out = q("SELECT COUNT(*) c FROM issued_books WHERE book_id=? AND status='Issued'", (pk,), one=True)["c"]
        if int(f["quantity"]) < out:
            return f"{out} copies are currently issued. Quantity cannot be lower than that."


def check_student(f, pk=None):
    if not all(f[k] for k in ("student_id", "name", "department", "email")):
        return "Please fill in Student ID, Name, Department and Email."
    if not EMAIL_RE.match(f["email"]):
        return "Enter a valid email address."
    if f["phone"] and not re.fullmatch(r"\d{7,15}", f["phone"]):
        return "Phone number must contain 7 to 15 digits."
    if q("SELECT id FROM students WHERE student_id=? AND id IS NOT ?", (f["student_id"], pk), one=True):
        return "Student ID already exists. Use a unique Student ID."


def login_required(view):
    @wraps(view)
    def wrapper(*a, **kw):
        if "user" not in session:
            flash("Please log in first.", "error")
            return redirect(url_for("login"))
        return view(*a, **kw)
    return wrapper


@app.template_filter("dmy")
def dmy(v):
    return date.fromisoformat(v).strftime("%d-%m-%Y") if v else "—"


@app.template_filter("days_text")
def days_text(n):
    if n < 0:
        return f"Overdue by {-n} day{'s' if n != -1 else ''}"
    return "Due today" if n == 0 else f"{n} day{'s' if n != 1 else ''}"


@app.template_filter("cls")
def cls(v):
    return str(v).lower().replace(" ", "-")


# ---------------------------------------------------------------- auth + public pages
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = q("SELECT * FROM users WHERE username=?", (request.form.get("username", "").strip(),), one=True)
        if user and check_password_hash(user["password"], request.form.get("password", "")):
            session["user"] = user["username"]
            return redirect(url_for("dashboard"))
        flash("Incorrect username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ---------------------------------------------------------------- dashboard
@app.route("/dashboard")
@login_required
def dashboard():
    issues = enrich(q(BASE_SQL + " ORDER BY i.id DESC"))
    active = [i for i in issues if i["state"] != "Returned"]
    overdue = [i for i in active if i["state"] == "Overdue"]
    soon = [i for i in active if i["state"] in ("Due Today", "Due Soon")]
    total_books = q("SELECT COALESCE(SUM(quantity),0) c FROM books", one=True)["c"]
    total_students = q("SELECT COUNT(*) c FROM students", one=True)["c"]
    cards = [
        ("Total Books", total_books, "fa-book", "c1"),
        ("Total Students", total_students, "fa-user-graduate", "c2"),
        ("Issued Books", len(active), "fa-book-open-reader", "c3"),
        ("Available Books", total_books - len(active), "fa-circle-check", "c4"),
        ("Due Soon", len(soon), "fa-bell", "c5"),
        ("Overdue Books", len(overdue), "fa-triangle-exclamation", "c6"),
        ("Total Fine", f"₹{sum(i['pending'] for i in issues)}", "fa-indian-rupee-sign", "c7"),
    ]
    chart = [len(active), len(issues) - len(active), len(overdue)]
    return render_template("dashboard.html", cards=cards, recent=issues[:8], soon=soon, overdue=overdue, chart=chart)


# ---------------------------------------------------------------- books
BOOK_FIELDS = ("book_id", "name", "author", "category", "isbn", "quantity")


@app.route("/books", methods=["GET", "POST"])
@login_required
def books():
    if request.method == "POST":
        f = {k: request.form.get(k, "").strip() for k in BOOK_FIELDS}
        err = check_book(f)
        if err:
            flash(err, "error")
        else:
            cur = run("INSERT INTO books(book_id,name,author,category,isbn,quantity) VALUES(?,?,?,?,?,?)",
                      (f["book_id"], f["name"], f["author"], f["category"], f["isbn"], int(f["quantity"])))
            refresh_book(cur.lastrowid)
            flash("Book added successfully.", "success")
        return redirect(url_for("books"))
    rows = q("""SELECT b.*, (SELECT COUNT(*) FROM issued_books i WHERE i.book_id=b.id AND i.status='Issued') AS out
                FROM books b ORDER BY b.id DESC""")
    cats = [r["category"] for r in q("SELECT DISTINCT category FROM books ORDER BY category")]
    return render_template("books.html", rows=rows, cats=cats)


@app.route("/books/edit/<int:pk>", methods=["POST"])
@login_required
def edit_book(pk):
    f = {k: request.form.get(k, "").strip() for k in BOOK_FIELDS}
    err = check_book(f, pk)
    if err:
        flash(err, "error")
    else:
        run("UPDATE books SET book_id=?,name=?,author=?,category=?,isbn=?,quantity=? WHERE id=?",
            (f["book_id"], f["name"], f["author"], f["category"], f["isbn"], int(f["quantity"]), pk))
        refresh_book(pk)
        flash("Book updated successfully.", "success")
    return redirect(url_for("books"))


@app.route("/books/delete/<int:pk>", methods=["POST"])
@login_required
def delete_book(pk):
    if q("SELECT id FROM issued_books WHERE book_id=?", (pk,), one=True):
        flash("This book has issue records and cannot be deleted.", "error")
    else:
        run("DELETE FROM books WHERE id=?", (pk,))
        flash("Book deleted successfully.", "success")
    return redirect(url_for("books"))


# ---------------------------------------------------------------- students
STUDENT_FIELDS = ("student_id", "name", "department", "email", "phone")


@app.route("/students", methods=["GET", "POST"])
@login_required
def students():
    if request.method == "POST":
        f = {k: request.form.get(k, "").strip() for k in STUDENT_FIELDS}
        err = check_student(f)
        if err:
            flash(err, "error")
        else:
            run("INSERT INTO students(student_id,name,department,email,phone) VALUES(?,?,?,?,?)",
                tuple(f[k] for k in STUDENT_FIELDS))
            flash("Student added successfully.", "success")
        return redirect(url_for("students"))
    rows = q("""SELECT s.*, (SELECT COUNT(*) FROM issued_books i WHERE i.student_id=s.id AND i.status='Issued') AS active,
                       (SELECT COUNT(*) FROM issued_books i WHERE i.student_id=s.id) AS total
                FROM students s ORDER BY s.id DESC""")
    return render_template("students.html", rows=rows)


@app.route("/students/edit/<int:pk>", methods=["POST"])
@login_required
def edit_student(pk):
    f = {k: request.form.get(k, "").strip() for k in STUDENT_FIELDS}
    err = check_student(f, pk)
    if err:
        flash(err, "error")
    else:
        run("UPDATE students SET student_id=?,name=?,department=?,email=?,phone=? WHERE id=?",
            tuple(f[k] for k in STUDENT_FIELDS) + (pk,))
        flash("Student updated successfully.", "success")
    return redirect(url_for("students"))


@app.route("/students/delete/<int:pk>", methods=["POST"])
@login_required
def delete_student(pk):
    if q("SELECT id FROM issued_books WHERE student_id=?", (pk,), one=True):
        flash("This student has issue records and cannot be deleted.", "error")
    else:
        run("DELETE FROM students WHERE id=?", (pk,))
        flash("Student deleted successfully.", "success")
    return redirect(url_for("students"))


# ---------------------------------------------------------------- issue / return
@app.route("/issue", methods=["GET", "POST"])
@login_required
def issue_book():
    if request.method == "POST":
        sid, bid = request.form.get("student"), request.form.get("book")
        try:
            issue_d = date.fromisoformat(request.form.get("issue_date", ""))
            due_d = date.fromisoformat(request.form.get("due_date", ""))
        except ValueError:
            issue_d = due_d = None
        book = q("SELECT * FROM books WHERE id=?", (bid,), one=True) if bid else None
        if not sid or not book or not issue_d or not due_d:
            flash("Please select a student and a book, and enter both dates.", "error")
        elif due_d < issue_d:
            flash("Due date cannot be before the issue date.", "error")
        elif book["status"] != "Available":
            flash("This book is not available to issue.", "error")
        else:
            run("INSERT INTO issued_books(student_id,book_id,issue_date,due_date) VALUES(?,?,?,?)",
                (sid, bid, issue_d.isoformat(), due_d.isoformat()))
            refresh_book(book["id"])
            flash("Book issued successfully.", "success")
        return redirect(url_for("issue_book"))
    today = date.today()
    return render_template(
        "issue_book.html",
        students=q("SELECT * FROM students ORDER BY name"),
        books=q("SELECT * FROM books WHERE status='Available' ORDER BY name"),
        today=today.isoformat(), due=(today + timedelta(days=14)).isoformat(),
        issues=[i for i in enrich(q(BASE_SQL + " ORDER BY i.id DESC")) if i["state"] != "Returned"])


@app.route("/return", methods=["GET", "POST"])
@login_required
def return_book():
    if request.method == "POST":
        issue = q("SELECT * FROM issued_books WHERE id=? AND status='Issued'", (request.form.get("issue_id"),), one=True)
        try:
            ret = date.fromisoformat(request.form.get("return_date", ""))
        except ValueError:
            ret = None
        if not issue or not ret:
            flash("Select an issued book and enter a valid return date.", "error")
        elif ret < date.fromisoformat(issue["issue_date"]):
            flash("Return date cannot be before the issue date.", "error")
        else:
            late = max((ret - date.fromisoformat(issue["due_date"])).days, 0)
            fine = late * FINE_PER_DAY
            run("UPDATE issued_books SET return_date=?, status='Returned', fine=? WHERE id=?",
                (ret.isoformat(), fine, issue["id"]))
            if fine > 0:
                run("INSERT INTO fines(issue_id,amount) VALUES(?,?)", (issue["id"], fine))
            refresh_book(issue["book_id"])
            flash("Book returned successfully." + (f" Late by {late} day(s). Fine: ₹{fine}." if fine else ""), "success")
        return redirect(url_for("return_book"))
    issues = [i for i in enrich(q(BASE_SQL + " ORDER BY i.due_date")) if i["state"] != "Returned"]
    return render_template("return_book.html", issues=issues, today=date.today().isoformat())


# ---------------------------------------------------------------- reminders (main feature)
@app.route("/reminders")
@login_required
def reminders():
    issues = enrich(q(BASE_SQL + " ORDER BY i.due_date"))
    due = [i for i in issues if i["state"] in ("Overdue", "Due Today", "Due Soon")]
    history = q("""SELECT r.*, s.name AS student_name, b.name AS book_name FROM reminders r
                   JOIN issued_books i ON i.id=r.issue_id JOIN students s ON s.id=i.student_id
                   JOIN books b ON b.id=i.book_id ORDER BY r.id DESC""")
    return render_template("reminders.html", due=due, history=history)


@app.route("/reminders/send/<int:issue_id>", methods=["POST"])
@login_required
def send_reminder(issue_id):
    rows = enrich(q(BASE_SQL + " WHERE i.id=?", (issue_id,)))
    if not rows or rows[0]["state"] == "Returned":
        flash("This book is not currently issued.", "error")
    elif deliver_reminder(rows[0]):
        run("INSERT INTO reminders(issue_id,reminder_date,status) VALUES(?,?,'Sent')",
            (issue_id, date.today().isoformat()))
        flash("Reminder sent successfully to the student.", "success")
    return redirect(url_for("reminders"))


# ---------------------------------------------------------------- overdue & fines
@app.route("/overdue")
@login_required
def overdue():
    rows = [i for i in enrich(q(BASE_SQL + " ORDER BY i.due_date"))
            if i["state"] == "Overdue" or (i["state"] == "Returned" and i["days_late"] > 0)]
    for r in rows:
        r["fine_amount"] = r["fine"] if r["state"] == "Returned" else r["days_late"] * FINE_PER_DAY
    per_student = {}
    for r in rows:
        if r["pending"]:
            per_student[r["student_name"]] = per_student.get(r["student_name"], 0) + r["pending"]
    depts = sorted({r["department"] for r in rows})
    paid = [r for r in rows if r["fine_status"] == "Paid"]
    return render_template("overdue.html", rows=rows, depts=depts, per_student=per_student, paid=paid,
                           total_pending=sum(r["pending"] for r in rows))


@app.route("/fines/pay/<int:issue_id>", methods=["POST"])
@login_required
def pay_fine(issue_id):
    run("UPDATE fines SET payment_status='Paid', payment_date=? WHERE issue_id=? AND payment_status='Pending'",
        (date.today().isoformat(), issue_id))
    flash("Fine marked as paid.", "success")
    return redirect(url_for("overdue"))


init_db()

if __name__ == "__main__":
    app.run(debug=True)
