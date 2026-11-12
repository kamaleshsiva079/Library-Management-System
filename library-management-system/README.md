# Library Management System
Knowledge Institute of Technology Library - a simple web app for library staff.

## Features
- Staff login (Flask sessions); all management pages are protected
- Dashboard with live statistics, Due Soon / Overdue lists, recent issues and a Chart.js chart
- Book management: add, edit, delete, live search, category filter
- Student management: add, view details, edit, delete, live search
- Issue books (blocked if unavailable; due date validation)
- Return books with automatic fine (late days x Rs. 5)
- **Due-Date Reminders (main feature):** due soon (3 days), due today and overdue books, "Send Reminder" button, reminder history. Delivery is simulated in `deliver_reminder()` in `app.py`, the place to add email/SMS later
- Overdue & Fine page: totals, fine per student, "Mark Fine Paid", payment history, department filter
- Toast notifications, validation, demo data created automatically

## Technologies
Python, Flask, SQLite, HTML, CSS, JavaScript, Chart.js

## Installation
```
python -m venv venv
venv\Scripts\activate          (Windows)
source venv/bin/activate       (macOS/Linux)
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

## Demo login
Username: admin
Password: admin123

To reset the demo data, stop the app, delete `database.db`, and start it again.
