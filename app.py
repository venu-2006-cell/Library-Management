from flask import Flask, request, jsonify
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1 import FieldFilter
import os

# =========================================================
# APP SETUP
# =========================================================
app = Flask(__name__)
CORS(app)

# =========================================================
# FIREBASE INIT
# =========================================================
if not firebase_admin._apps:
    if not os.path.exists("firebase_key.json"):
        raise FileNotFoundError("firebase_key.json not found")
    cred = credentials.Certificate("firebase_key.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# =========================================================
# CHECK BOOK AVAILABILITY
# =========================================================
@app.route("/check-book-availability", methods=["POST"])
def check_book_availability():
    data = request.get_json(force=True)
    book_id = data.get("book_id")

    if not book_id:
        return jsonify({"error": "book_id is required"}), 400

    # Fetch book
    book_ref = db.collection("books").document(book_id)
    book_doc = book_ref.get()

    if not book_doc.exists:
        return jsonify({"error": "Book not found"}), 404

    book_data = book_doc.to_dict()
    total_copies = book_data.get("total_copies", 0)

    # Count issued copies
    issued_query = (
        db.collection("issues")
        .where(filter=FieldFilter("book_id", "==", book_id))
        .where(filter=FieldFilter("status", "==", "issued"))
    )

    issued_count = len(list(issued_query.stream()))

    available_copies = total_copies - issued_count

    return jsonify({
        "book_id": book_id,
        "book_name": book_data.get("book_name"),
        "author": book_data.get("author"),
        "department": book_data.get("department"),
        "total_copies": total_copies,
        "issued_copies": issued_count,
        "available_copies": max(available_copies, 0),
        "available": available_copies > 0
    })

# =========================================================
# RUN SERVER
# =========================================================
if __name__ == "__main__":
    app.run(debug=True)
