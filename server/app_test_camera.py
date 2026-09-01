from flask import Flask, request, jsonify
import os
import shutil
from datetime import datetime

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))

UPLOAD_FOLDER = os.path.join(ROOT_DIR, "uploads")
STATIC_UPLOAD_FOLDER = os.path.join(ROOT_DIR, "static", "uploads")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_UPLOAD_FOLDER, exist_ok=True)

@app.route("/")
def home():
    return jsonify({"status": "ready", "message": "Camera Server Running"}), 200

def save_image_bytes(raw_bytes):
    filename = datetime.now().strftime("%Y%m%d_%H%M%S.jpg")
    save_path_root = os.path.join(UPLOAD_FOLDER, filename)
    save_path_static = os.path.join(STATIC_UPLOAD_FOLDER, filename)
    save_path_latest = os.path.join(STATIC_UPLOAD_FOLDER, "latest_camera.jpg")

    # 1. Simpan di root uploads/
    with open(save_path_root, "wb") as f:
        f.write(raw_bytes)

    # 2. Simpan di static/uploads/
    with open(save_path_static, "wb") as f:
        f.write(raw_bytes)

    # 3. Simpan di static/uploads/latest_camera.jpg (untuk tampilan web live)
    with open(save_path_latest, "wb") as f:
        f.write(raw_bytes)

    print(f"[RAW JPEG] Foto tersimpan ({len(raw_bytes)} bytes) di:")
    print(f" -> {save_path_root}")
    print(f" -> {save_path_static}")
    return filename

@app.route("/camera/upload", methods=["POST"])
def upload_camera():
    # 1. Handle Multipart Form Data (request.files)
    if "image" in request.files:
        file = request.files["image"]
        raw_bytes = file.read()
        filename = save_image_bytes(raw_bytes)
        return jsonify({"status": "success", "filename": filename, "size": len(raw_bytes)}), 200

    # 2. Handle Raw Binary JPEG Payload (http.POST(fb->buf, fb->len))
    raw_data = request.get_data()
    if raw_data and len(raw_data) > 0:
        filename = save_image_bytes(raw_data)
        return jsonify({"status": "success", "filename": filename, "size": len(raw_data)}), 200

    print("[UPLOAD ERROR] No image data received")
    return jsonify({"status": "error", "message": "No image data found in request"}), 400

if __name__ == "__main__":
    print("[CAMERA TEST] Starting Camera Server on http://0.0.0.0:5001 ...")
    app.run(host="0.0.0.0", port=5001, debug=True)