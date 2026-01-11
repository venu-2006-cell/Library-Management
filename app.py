from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore
import os
import pandas as pd
from datetime import datetime
import threading
import webview
import sys
import csv



# -------------------------------------------------
# App Setup
# -------------------------------------------------
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS  # PyInstaller temp folder
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

app = Flask(
    __name__,
    template_folder=resource_path("templates")
)
# -------------------------------------------------
# Firebase Initialization
# -------------------------------------------------
firebase_path = resource_path("firebase_key.json")

if not os.path.exists(firebase_path):
    raise FileNotFoundError("firebase_key.json not found!")

cred = credentials.Certificate(firebase_path)
firebase_admin.initialize_app(cred)

 

db = firestore.client()

# -------------------------------------------------
# LOGIN ROUTE
# -------------------------------------------------
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"success": False, "message": "Username and password required"}), 400

    user_ref = db.collection("users").document(username).get()
    if user_ref.exists:
        user_data = user_ref.to_dict()
        if user_data.get("password") == password:
            return jsonify({
                "success": True,
                "message": "Login successful",
                "user": {"username": username, "role": user_data.get("role", "admin")}
            }), 200

    return jsonify({"success": False, "message": "Invalid credentials"}), 401

# -------------------------------------------------
# HOME ROUTE (Frontend)
# -------------------------------------------------
@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

@app.route("/student", methods=["GET"])
def student_page():
    return render_template("student.html")


    

# -------------------------------------------------
# BOOK ROUTES
# -------------------------------------------------
@app.route("/add-book", methods=["POST"])
def add_book():
    data = request.get_json()
    book_id = data.get("book_id")
    title = data.get("title")
    author = data.get("author")
    department = data.get("department")

    try:
        total_copies = int(data.get("total_copies"))
    except:
        return jsonify({"error": "Total copies must be a number"}), 400

    if not all([book_id, title, author, department]):
        return jsonify({"error": "All fields required"}), 400

    db.collection("books").document(book_id).set({
        "title": title,
        "author": author,
        "department": department,
        "total_copies": total_copies,
        "available_copies": total_copies
    })

    return jsonify({"message": "Book added successfully"})

@app.route("/books", methods=["GET"])
def view_books():
    books = []
    for b in db.collection("books").stream():
        d = b.to_dict()
        d["book_id"] = b.id
        books.append(d)
    return jsonify(books)

@app.route("/delete-book/<book_id>", methods=["DELETE"])
def delete_book(book_id):
    book_ref = db.collection("books").document(book_id)
    book_doc = book_ref.get()

    if not book_doc.exists:
        return jsonify({"error": "Book not found"}), 404

    txs = db.collection("transactions").where("book_id", "==", book_id).stream()
    for tx in txs:
        db.collection("transactions").document(tx.id).delete()

    book_ref.delete()
    return jsonify({"message": f"Book {book_id} deleted successfully"})

# -------------------------------------------------
# STUDENT ROUTES
# -------------------------------------------------
@app.route("/add-student", methods=["POST"])
def add_student():
    data = request.get_json()
    roll_no = data.get("roll_no")
    reg_no = data.get("reg_no")
    student_name = data.get("student_name")
    department = data.get("department")

    if not all([roll_no, reg_no, student_name, department]):
        return jsonify({"error": "All fields required"}), 400

    db.collection("students").document(roll_no).set({
        "reg_no": reg_no,
        "student_name": student_name,
        "department": department
    })

    return jsonify({"message": "Student added successfully"})

@app.route("/students", methods=["GET"])
def view_students():
    students = []
    for s in db.collection("students").stream():
        d = s.to_dict()
        d["roll_no"] = s.id
        students.append(d)
    return jsonify(students)

@app.route("/delete-student/<roll_no>", methods=["DELETE"])
def delete_student(roll_no):
    student_ref = db.collection("students").document(roll_no)
    if not student_ref.get().exists:
        return jsonify({"error": "Student not found"}), 404

    txs = db.collection("transactions").where("roll_no", "==", roll_no).stream()
    for tx in txs:
        db.collection("transactions").document(tx.id).delete()

    student_ref.delete()
    return jsonify({"message": "Student deleted successfully"})

# -------------------------------------------------
# ISSUE BOOK
# -------------------------------------------------
@app.route("/issue-book", methods=["POST"])
def issue_book():
    data = request.get_json()
    roll_no = data.get("roll_no")
    book_id = data.get("book_id")

    if not roll_no or not book_id:
        return jsonify({"error": "Roll No & Book ID required"}), 400

    if not db.collection("students").document(roll_no).get().exists:
        return jsonify({"error": "Student not found"}), 404

    book_ref = db.collection("books").document(book_id)
    book = book_ref.get()
    if not book.exists:
        return jsonify({"error": "Book not found"}), 404

    book_data = book.to_dict()
    if book_data["available_copies"] <= 0:
        return jsonify({"error": "No copies available"}), 400

    book_ref.update({"available_copies": book_data["available_copies"] - 1})

    db.collection("transactions").add({
        "roll_no": roll_no,
        "book_id": book_id,
        "status": "ISSUED",
        "issue_date": datetime.now().strftime("%Y-%m-%d"),
        "return_date": None
    })

    return jsonify({"message": "Book issued successfully"})

# -------------------------------------------------
# RETURN BOOK
# -------------------------------------------------
@app.route("/return-book/<tx_id>", methods=["PUT"])
def return_book(tx_id):
    tx_ref = db.collection("transactions").document(tx_id)
    tx = tx_ref.get()

    if not tx.exists:
        return jsonify({"error": "Transaction not found"}), 404

    tx_data = tx.to_dict()
    if tx_data["status"] == "RETURNED":
        return jsonify({"error": "Already returned"}), 400

    tx_ref.update({
        "status": "RETURNED",
        "return_date": datetime.now().strftime("%Y-%m-%d")
    })

    db.collection("books").document(tx_data["book_id"]).update({
        "available_copies": firestore.Increment(1)
    })

    return jsonify({"message": "Book returned successfully"})

# -------------------------------------------------
# VIEW ISSUED BOOKS
# -------------------------------------------------
@app.route("/issued-books", methods=["GET"])
def issued_books():
    result = []
    txs = db.collection("transactions").where("status", "==", "ISSUED").stream()

    for t in txs:
        d = t.to_dict()
        roll_no = d.get("roll_no")

        # Fetch student details
        student_doc = db.collection("students").document(roll_no).get()
        if student_doc.exists:
            student = student_doc.to_dict()
            d["student_name"] = student.get("student_name", "Unknown")
            d["student_dept"] = student.get("department", "N/A")
        else:
            d["student_name"] = "Unknown"
            d["student_dept"] = "N/A"

        d["tx_id"] = t.id
        result.append(d)

    return jsonify(result)


# -------------------------------------------------
# EXPORT BOOKS
# -------------------------------------------------


@app.route("/export-books", methods=["GET"])
def export_books():
    rows = []
    for b in db.collection("books").stream():
        d = b.to_dict()
        d["book_id"] = b.id
        rows.append(d)

    if not rows:
        return jsonify({"error": "No data to export"}), 400

    filename = "books_export.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    return send_file(filename, as_attachment=True)


# -------------------------------------------------
# Flask Thread
# -------------------------------------------------
def run_flask():
    app.run(host="127.0.0.1", port=5000, debug=False)

# -------------------------------------------------
# Desktop App Start
# -------------------------------------------------
if __name__ == "__main__":
    print("🚀 Starting Library Desktop App - app.py:305")

    # Run Flask in background
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # Launch Desktop Window with frontend
    webview.create_window(
        "Library Management System",
        "http://127.0.0.1:5000",
        width=1200,
        height=800
    )

    webview.start(gui="edgechromium")
