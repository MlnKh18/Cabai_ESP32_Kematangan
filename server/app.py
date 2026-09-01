import os
import sqlite3
import time
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS

import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image

# Setup Flask App pointing to dashboard directory for static frontend
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, '..'))
DASHBOARD_DIR = os.path.join(ROOT_DIR, 'dashboard')
DB_PATH = os.path.join(BASE_DIR, 'database.db')

UPLOAD_DIR = os.path.join(ROOT_DIR, 'uploads')
STATIC_UPLOAD_DIR = os.path.join(ROOT_DIR, 'static', 'uploads')
MODEL_PATH = os.path.join(ROOT_DIR, 'model_cabe_mobilenet.pth')

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(STATIC_UPLOAD_DIR, exist_ok=True)

app = Flask(__name__, static_folder=DASHBOARD_DIR, static_url_path='')
CORS(app)

# ---------------------------------------------------------
# 1. AI MOBILENET MODEL INITIALIZATION
# ---------------------------------------------------------
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

CLASS_JSON_PATH = os.path.join(ROOT_DIR, 'class_names.json')
TRAIN_DIR_PATH = os.path.join(ROOT_DIR, 'dataset', 'train')

class_names = ['Dry chili', 'Flower', 'Green Chili', 'Red Chili', 'Rotten Chili']
if os.path.exists(CLASS_JSON_PATH):
    import json
    with open(CLASS_JSON_PATH, 'r') as f:
        class_names = json.load(f)
elif os.path.exists(TRAIN_DIR_PATH):
    class_names = sorted([d for d in os.listdir(TRAIN_DIR_PATH) if os.path.isdir(os.path.join(TRAIN_DIR_PATH, d))])

ai_model = None
if os.path.exists(MODEL_PATH):
    try:
        ai_model = models.mobilenet_v3_large()
        ai_model.classifier[3] = nn.Linear(ai_model.classifier[3].in_features, len(class_names))
        ai_model.load_state_dict(torch.load(MODEL_PATH, map_location=DEVICE))
        ai_model.to(DEVICE)
        ai_model.eval()
        print(f"[AI MODEL] MobileNetV3 AI classifier loaded with {len(class_names)} classes: {class_names}")
    except Exception as e:
        print(f"[AI MODEL ERROR] Failed to load model: {e}")

transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

def classify_image(img_path):
    if ai_model is None:
        return {"class": "Model AI Belum Di-load", "confidence": "0.00%"}
    try:
        img = Image.open(img_path).convert('RGB')
        img_t = transform(img).unsqueeze(0).to(DEVICE)
        with torch.no_grad():
            outputs = ai_model(img_t)
            prob = torch.nn.functional.softmax(outputs[0], dim=0)
            confidence, index = torch.max(prob, 0)
        
        raw_class = class_names[index.item()]
        
        # Mapping nama kelas ke Bahasa Indonesia yang presisi
        label_map = {
            "Cabe_Merah": "Cabe Merah (Matang)",
            "Cabe_Kuning": "Cabe Kuning (Setengah Matang)",
            "Cabe_Hijau": "Cabe Hijau (Belum Matang)",
            "Red Chili": "Cabe Merah (Matang)",
            "Green Chili": "Cabe Hijau (Belum Matang)"
        }
        display_label = label_map.get(raw_class, raw_class.replace('_', ' '))
        
        return {
            "class": display_label,
            "raw_class": raw_class,
            "confidence": f"{confidence.item()*100:.2f}%"
        }
    except Exception as e:
        return {"class": f"Error Prediksi: {e}", "confidence": "0.00%"}

# Global state camera
latest_capture_data = {
    "filename": "",
    "timestamp": "",
    "ai_result": None
}

# ---------------------------------------------------------
# 2. DATABASE INITIALIZATION
# ---------------------------------------------------------
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sensor_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            temperature REAL,
            humidity REAL,
            soil_moisture REAL,
            light_intensity REAL,
            pump_status INTEGER,
            auto_mode INTEGER
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS control_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            auto_mode INTEGER DEFAULT 1,
            pump_override INTEGER DEFAULT 0,
            moisture_threshold REAL DEFAULT 40.0,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        INSERT OR IGNORE INTO control_settings (id, auto_mode, pump_override, moisture_threshold)
        VALUES (1, 1, 0, 40.0)
    ''')
    
    conn.commit()
    conn.close()

init_db()

# ---------------------------------------------------------
# 3. FRONTEND DASHBOARD ROUTES
# ---------------------------------------------------------
@app.route('/')
def serve_dashboard():
    return send_from_directory(DASHBOARD_DIR, 'index.html')

@app.route('/uploads/<filename>')
def serve_uploaded_file(filename):
    return send_from_directory(STATIC_UPLOAD_DIR, filename)

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory(DASHBOARD_DIR, filename)

# ---------------------------------------------------------
# 4. ESP32-CAM STREAM & UPLOAD ENDPOINTS
# ---------------------------------------------------------

# Global state camera
esp32_cam_ip = ""

@app.route('/api/camera/announce', methods=['GET', 'POST'])
def announce_camera_ip():
    global esp32_cam_ip
    cam_ip = request.args.get('ip') or (request.json.get('ip') if request.is_json else None)
    if cam_ip:
        esp32_cam_ip = cam_ip
        print(f"[CAMERA SERVER] ESP32-CAM IP Announced: {esp32_cam_ip}")
        return jsonify({"status": "success", "cam_ip": esp32_cam_ip}), 200
    return jsonify({"status": "error", "message": "IP missing"}), 400

# Endpoint reception for raw uploads if fallback needed
@app.route('/camera/upload', methods=['POST'])
def upload_camera_photo():
    try:
        raw_data = None
        if 'image' in request.files:
            raw_data = request.files['image'].read()
        else:
            raw_data = request.get_data()

        if raw_data and len(raw_data) > 0:
            latest_path = os.path.join(STATIC_UPLOAD_DIR, "latest_camera.jpg")
            with open(latest_path, "wb") as f:
                f.write(raw_data)
            return jsonify({"status": "success", "message": "Frame received", "size": len(raw_data)}), 200
        return jsonify({"status": "error", "message": "No image data found"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Endpoint Live Stream MJPEG Proxy untuk Web Dashboard (25-30 FPS Zero-Lag)
@app.route('/camera/live')
def serve_live_camera():
    global esp32_cam_ip
    if esp32_cam_ip:
        return jsonify({"stream_url": f"http://{esp32_cam_ip}/stream", "capture_url": f"http://{esp32_cam_ip}/capture"})
    
    latest_path = os.path.join(STATIC_UPLOAD_DIR, "latest_camera.jpg")
    if os.path.exists(latest_path):
        return send_file(latest_path, mimetype='image/jpeg')
    return send_from_directory(DASHBOARD_DIR, 'index.html'), 404

# Endpoint Web Action: Hapus foto & Reset ke mode live stream ESP32-CAM
@app.route('/api/camera/reset-live', methods=['POST'])
def reset_camera_to_live():
    try:
        global latest_capture_data
        latest_capture_data = {
            "filename": "",
            "timestamp": "",
            "ai_result": None
        }
        latest_path = os.path.join(STATIC_UPLOAD_DIR, "latest_camera.jpg")
        if os.path.exists(latest_path):
            os.remove(latest_path)

        print("[CAMERA SERVER] Reset to Live Stream Mode")
        return jsonify({"status": "success", "message": "Kembali ke mode live stream ESP32-CAM"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Endpoint Web Action: Manual Upload Foto untuk Pengujian AI
@app.route('/api/camera/test-upload', methods=['POST'])
def test_upload_image_ai():
    try:
        file = request.files.get('file') or request.files.get('image')
        if not file:
            return jsonify({"status": "error", "message": "File foto tidak ditemukan dalam request."}), 400

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"upload_test_{timestamp_str}_{file.filename}"
        save_path_root = os.path.join(UPLOAD_DIR, filename)
        save_path_static = os.path.join(STATIC_UPLOAD_DIR, filename)
        latest_path = os.path.join(STATIC_UPLOAD_DIR, "latest_camera.jpg")

        file.save(save_path_root)
        # Salin ke static & latest_camera.jpg
        with open(save_path_root, "rb") as fsrc:
            bdata = fsrc.read()
        with open(save_path_static, "wb") as fdst:
            fdst.write(bdata)
        with open(latest_path, "wb") as fdst:
            fdst.write(bdata)

        # Jalankan Klasifikasi AI MobileNet
        ai_res = classify_image(save_path_static)

        global latest_capture_data
        latest_capture_data = {
            "filename": filename,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "ai_result": ai_res
        }

        print(f"[TEST UPLOAD AI] Photo: {filename} -> Class: {ai_res['class']} ({ai_res['confidence']})")

        return jsonify({
            "status": "success",
            "filename": filename,
            "image_url": f"/uploads/{filename}",
            "ai_result": ai_res,
            "timestamp": latest_capture_data["timestamp"]
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Endpoint Web Action: Tombol "Ambil Foto Kamera & Deteksi AI"
@app.route('/api/camera/capture', methods=['POST'])
def trigger_camera_capture_and_ai():
    global esp32_cam_ip
    frame_data = None

    # Option 1: Ambil foto langsung dari ESP32-CAM /capture endpoint jika IP terdeteksi
    if esp32_cam_ip:
        import urllib.request
        try:
            req = urllib.request.urlopen(f"http://{esp32_cam_ip}/capture", timeout=3)
            frame_data = req.read()
        except Exception as err:
            print(f"[CAM CAPTURE WARNING] Direct IP capture failed ({err}), trying fallback file...")

    # Option 2: Fallback ke file latest_camera.jpg
    latest_path = os.path.join(STATIC_UPLOAD_DIR, "latest_camera.jpg")
    if frame_data is None and os.path.exists(latest_path):
        with open(latest_path, "rb") as f:
            frame_data = f.read()

    # Option 3: Fallback ke gambar sampel validasi jika belum ada file kamera
    if frame_data is None:
        sample_path = os.path.join(ROOT_DIR, 'dataset', 'val', 'Cabe_Merah', 'merah_val_0.jpg')
        if not os.path.exists(sample_path):
            sample_path = os.path.join(ROOT_DIR, 'dataset', 'val', 'Cabe_Hijau', 'hijau_val_0.jpg')
        if os.path.exists(sample_path):
            with open(sample_path, "rb") as f:
                frame_data = f.read()

    if not frame_data:
        from PIL import Image
        import io
        img = Image.new('RGB', (320, 240), color=(180, 50, 50))
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        frame_data = buf.getvalue()

    if not frame_data:
        return jsonify({
            "status": "error",
            "message": "Kamera ESP32 belum terhubung. Pastikan ESP32-CAM menyala dan terhubung ke WiFi."
        }), 400

    try:
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"snapshot_{timestamp_str}.jpg"
        save_path_root = os.path.join(UPLOAD_DIR, filename)
        save_path_static = os.path.join(STATIC_UPLOAD_DIR, filename)

        # Simpan snapshot permanen
        with open(save_path_root, "wb") as f:
            f.write(frame_data)
        with open(save_path_static, "wb") as f:
            f.write(frame_data)

        # Jalankan Klasifikasi AI MobileNet
        ai_res = classify_image(save_path_static)

        global latest_capture_data
        latest_capture_data = {
            "filename": filename,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "ai_result": ai_res
        }

        print(f"[CAM CAPTURE & AI] Snapshot: {filename} -> Class: {ai_res['class']} ({ai_res['confidence']})")

        return jsonify({
            "status": "success",
            "filename": filename,
            "image_url": f"/uploads/{filename}",
            "ai_result": ai_res,
            "timestamp": latest_capture_data["timestamp"]
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/camera/latest', methods=['GET'])
def get_latest_camera_status():
    return jsonify({
        "active": bool(esp32_cam_ip or os.path.exists(os.path.join(STATIC_UPLOAD_DIR, "latest_camera.jpg"))),
        "cam_ip": esp32_cam_ip,
        "latest_capture": latest_capture_data
    })

# ---------------------------------------------------------
# 5. TELEMETRY SENSOR & CONTROL ENDPOINTS
# ---------------------------------------------------------

@app.route('/api/sensor-data', methods=['POST'])
def receive_sensor_data():
    try:
        data = request.get_json(force=True)
        temp = data.get('temperature', 0.0)
        hum = data.get('humidity', 0.0)
        soil = data.get('soil_moisture', 0.0)
        light = data.get('light_intensity', 0.0)
        pump = 1 if data.get('pump_status', False) else 0

        conn = get_db_connection()
        cursor = conn.cursor()

        setting = cursor.execute('SELECT auto_mode FROM control_settings WHERE id = 1').fetchone()
        auto_mode = setting['auto_mode'] if setting else 1

        cursor.execute('''
            INSERT INTO sensor_logs (temperature, humidity, soil_moisture, light_intensity, pump_status, auto_mode)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (temp, hum, soil, light, pump, auto_mode))
        
        conn.commit()
        conn.close()

        return jsonify({
            "status": "success",
            "message": "Data saved successfully",
            "controls": get_control_status_dict()
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/data/latest', methods=['GET'])
def get_latest_data():
    conn = get_db_connection()
    row = conn.execute('SELECT * FROM sensor_logs ORDER BY id DESC LIMIT 1').fetchone()
    conn.close()

    if row:
        data = {
            "id": row["id"],
            "timestamp": row["timestamp"],
            "temperature": row["temperature"],
            "humidity": row["humidity"],
            "soil_moisture": row["soil_moisture"],
            "light_intensity": row["light_intensity"],
            "pump_status": bool(row["pump_status"]),
            "auto_mode": bool(row["auto_mode"])
        }
    else:
        data = {
            "id": 0,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "temperature": 28.0,
            "humidity": 60.0,
            "soil_moisture": 45.0,
            "light_intensity": 0.0,
            "pump_status": False,
            "auto_mode": True
        }

    control = get_control_status_dict()
    return jsonify({
        "sensor": data,
        "control": control,
        "camera": latest_capture_data
    })

@app.route('/api/data/history', methods=['GET'])
def get_history_data():
    limit = request.args.get('limit', 15, type=int)
    conn = get_db_connection()
    rows = conn.execute('SELECT * FROM sensor_logs ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
    conn.close()

    history = []
    for r in reversed(rows):
        history.append({
            "timestamp": r["timestamp"].split(" ")[1] if " " in str(r["timestamp"]) else str(r["timestamp"]),
            "temperature": r["temperature"],
            "humidity": r["humidity"],
            "soil_moisture": r["soil_moisture"],
            "light_intensity": r["light_intensity"],
            "pump_status": bool(r["pump_status"])
        })

    return jsonify({"history": history})

def get_control_status_dict():
    conn = get_db_connection()
    row = conn.execute('SELECT * FROM control_settings WHERE id = 1').fetchone()
    conn.close()
    if row:
        return {
            "auto_mode": bool(row["auto_mode"]),
            "pump_override": bool(row["pump_override"]),
            "moisture_threshold": row["moisture_threshold"]
        }
    return {"auto_mode": True, "pump_override": False, "moisture_threshold": 40.0}

@app.route('/api/control', methods=['GET', 'POST'])
def control_api():
    if request.method == 'GET':
        return jsonify(get_control_status_dict())

    if request.method == 'POST':
        try:
            data = request.get_json(force=True)
            conn = get_db_connection()
            cursor = conn.cursor()

            if 'auto_mode' in data:
                cursor.execute('UPDATE control_settings SET auto_mode = ?, last_updated = CURRENT_TIMESTAMP WHERE id = 1',
                               (1 if data['auto_mode'] else 0,))
            if 'pump_override' in data:
                cursor.execute('UPDATE control_settings SET pump_override = ?, last_updated = CURRENT_TIMESTAMP WHERE id = 1',
                               (1 if data['pump_override'] else 0,))
            if 'moisture_threshold' in data:
                cursor.execute('UPDATE control_settings SET moisture_threshold = ?, last_updated = CURRENT_TIMESTAMP WHERE id = 1',
                               (float(data['moisture_threshold']),))

            conn.commit()
            conn.close()
            return jsonify({"status": "success", "controls": get_control_status_dict()})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    print(f"[CABAI_IOT] Starting Server on http://0.0.0.0:{port} ...")
    app.run(host='0.0.0.0', port=port, debug=True)
