import os
import shutil
import random
import zipfile
from io import BytesIO
from PIL import Image, ImageEnhance

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ZIP_PATH = "C:/Users/maula/Downloads/Chili Growth Stage Original Dataset.zip"
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
TRAIN_DIR = os.path.join(DATASET_DIR, "train")
VAL_DIR = os.path.join(DATASET_DIR, "val")

TARGET_CLASSES = ['Cabe_Hijau', 'Cabe_Kuning', 'Cabe_Merah']

def setup_3_classes_dataset():
    print("=== EKSTRAKSI DATASET & PEMBAGIAN 3 KELAS KEMATANGAN (80:20 SPLIT) ===")
    
    # 1. Clean dataset directory
    shutil.rmtree(DATASET_DIR, ignore_errors=True)
    for c in TARGET_CLASSES:
        os.makedirs(os.path.join(TRAIN_DIR, c), exist_ok=True)
        os.makedirs(os.path.join(VAL_DIR, c), exist_ok=True)

    # 2. Extract Green Chili and Red Chili images from zip
    print(f" [*] Membaca arsip dataset: {ZIP_PATH} ...")
    zf = zipfile.ZipFile(ZIP_PATH)

    green_bytes = []
    red_bytes = []

    for name in zf.namelist():
        if name.lower().endswith(('.jpg', '.jpeg', '.png')):
            # Filter Green Chili
            if '/green chili/' in name.lower() or 'green chili' in name.lower():
                green_bytes.append((os.path.basename(name), zf.read(name)))
            # Filter Red Chili
            elif '/red chili/' in name.lower() or 'red chili' in name.lower():
                red_bytes.append((os.path.basename(name), zf.read(name)))

    print(f" -> Ditemukan {len(green_bytes)} foto Cabe Hijau (Belum Matang)")
    print(f" -> Ditemukan {len(red_bytes)} foto Cabe Merah (Matang)")

    random.seed(42)

    # 3. Process & Split Cabe Hijau (80:20)
    random.shuffle(green_bytes)
    val_cnt_g = int(len(green_bytes) * 0.20)
    val_g = green_bytes[:val_cnt_g]
    train_g = green_bytes[val_cnt_g:]

    for idx, (fname, bdata) in enumerate(train_g):
        with open(os.path.join(TRAIN_DIR, 'Cabe_Hijau', f"hijau_train_{idx}.jpg"), 'wb') as f:
            f.write(bdata)
    for idx, (fname, bdata) in enumerate(val_g):
        with open(os.path.join(VAL_DIR, 'Cabe_Hijau', f"hijau_val_{idx}.jpg"), 'wb') as f:
            f.write(bdata)

    # 4. Process & Split Cabe Merah (80:20)
    random.shuffle(red_bytes)
    val_cnt_r = int(len(red_bytes) * 0.20)
    val_r = red_bytes[:val_cnt_r]
    train_r = red_bytes[val_cnt_r:]

    for idx, (fname, bdata) in enumerate(train_r):
        with open(os.path.join(TRAIN_DIR, 'Cabe_Merah', f"merah_train_{idx}.jpg"), 'wb') as f:
            f.write(bdata)
    for idx, (fname, bdata) in enumerate(val_r):
        with open(os.path.join(VAL_DIR, 'Cabe_Merah', f"merah_val_{idx}.jpg"), 'wb') as f:
            f.write(bdata)

    # 5. Process & Generate Cabe Kuning (Hampir Matang / Transisi 80:20)
    print(" [*] Memproses sampel Cabe Kuning (Hampir Matang)...")
    kuning_sources = train_r[:150] + train_g[:150]
    random.shuffle(kuning_sources)
    val_cnt_k = int(len(kuning_sources) * 0.20)
    val_k = kuning_sources[:val_cnt_k]
    train_k = kuning_sources[val_cnt_k:]

    def save_yellow_image(raw_bdata, dst_path):
        try:
            img = Image.open(BytesIO(raw_bdata)).convert('RGB')
            r, g, b = img.split()
            r_yellow = ImageEnhance.Brightness(r).enhance(1.1)
            g_yellow = ImageEnhance.Brightness(g).enhance(1.05)
            b_yellow = ImageEnhance.Brightness(b).enhance(0.7)
            yellow_img = Image.merge('RGB', (r_yellow, g_yellow, b_yellow))
            yellow_img.save(dst_path, quality=92)
        except Exception:
            with open(dst_path, 'wb') as f:
                f.write(raw_bdata)

    for idx, (fname, bdata) in enumerate(train_k):
        save_yellow_image(bdata, os.path.join(TRAIN_DIR, 'Cabe_Kuning', f"kuning_train_{idx}.jpg"))
    for idx, (fname, bdata) in enumerate(val_k):
        save_yellow_image(bdata, os.path.join(VAL_DIR, 'Cabe_Kuning', f"kuning_val_{idx}.jpg"))

    zf.close()

    print("\n==================================================")
    print(" [OK] Dataset 3 Kelas Kematangan Selesai Disiapkan!")
    print("==================================================")
    for c in TARGET_CLASSES:
        tr_n = len(os.listdir(os.path.join(TRAIN_DIR, c)))
        vl_n = len(os.listdir(os.path.join(VAL_DIR, c)))
        print(f" * {c:15s} -> Train (80%): {tr_n:3d} foto | Val (20%): {vl_n:3d} foto")
    print("==================================================")

if __name__ == '__main__':
    setup_3_classes_dataset()
