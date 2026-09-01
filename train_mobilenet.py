import os
import time
import copy
import json
import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import datasets, models, transforms
from torch.utils.data import DataLoader
from PIL import Image

# ---------------------------------------------------------
# 1. KONFIGURASI PARAMETER TRAINING
# ---------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
TRAIN_DIR = os.path.join(DATASET_DIR, "train")
VAL_DIR = os.path.join(DATASET_DIR, "val")
MODEL_SAVE_PATH = os.path.join(BASE_DIR, "model_cabe_mobilenet.pth")
CLASS_SAVE_PATH = os.path.join(BASE_DIR, "class_names.json")

BATCH_SIZE = 16
NUM_EPOCHS = 10
LEARNING_RATE = 0.001

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# ---------------------------------------------------------
# 2. TRANSFORMASI & AUGMENTASI GAMBAR
# ---------------------------------------------------------
data_transforms = {
    'train': transforms.Compose([
        transforms.RandomResizedCrop(224, scale=(0.8, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(15),
        transforms.ColorJitter(brightness=0.2, contrast=0.2),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ]),
    'val': transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ]),
}

def load_data():
    image_datasets = {
        'train': datasets.ImageFolder(TRAIN_DIR, data_transforms['train']),
        'val': datasets.ImageFolder(VAL_DIR, data_transforms['val'])
    }
    dataloaders = {
        'train': DataLoader(image_datasets['train'], batch_size=BATCH_SIZE, shuffle=True, num_workers=0),
        'val': DataLoader(image_datasets['val'], batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
    }
    dataset_sizes = {x: len(image_datasets[x]) for x in ['train', 'val']}
    class_names = image_datasets['train'].classes

    # Simpan nama kelas ke JSON
    with open(CLASS_SAVE_PATH, 'w') as f:
        json.dump(class_names, f)

    return dataloaders, dataset_sizes, class_names

# ---------------------------------------------------------
# 3. BUILD MODEL MOBILENETV3 LARGE
# ---------------------------------------------------------
def build_mobilenet_model(num_classes):
    print(f" [*] Inisialisasi Arsitektur MobileNetV3 Large ({num_classes} Kelas) di {DEVICE}...")
    
    # Pretrained MobileNetV3
    weights = models.MobileNet_V3_Large_Weights.DEFAULT
    model = models.mobilenet_v3_large(weights=weights)

    # Sesuaikan layer classifier terakhir ke jumlah kelas cabai (3 kelas)
    in_features = model.classifier[3].in_features
    model.classifier[3] = nn.Linear(in_features, num_classes)
    
    model = model.to(DEVICE)
    return model

# ---------------------------------------------------------
# 4. TRAINING & EVALUASI MODEL
# ---------------------------------------------------------
def train_model(model, dataloaders, dataset_sizes, criterion, optimizer, scheduler, num_epochs=10):
    since = time.time()
    best_model_wts = copy.deepcopy(model.state_dict())
    best_acc = 0.0

    for epoch in range(num_epochs):
        print(f"\n --- Epoch {epoch + 1}/{num_epochs} ---")

        for phase in ['train', 'val']:
            if phase == 'train':
                model.train()
            else:
                model.eval()

            running_loss = 0.0
            running_corrects = 0

            for inputs, labels in dataloaders[phase]:
                inputs = inputs.to(DEVICE)
                labels = labels.to(DEVICE)

                optimizer.zero_grad()

                with torch.set_grad_enabled(phase == 'train'):
                    outputs = model(inputs)
                    _, preds = torch.max(outputs, 1)
                    loss = criterion(outputs, labels)

                    if phase == 'train':
                        loss.backward()
                        optimizer.step()

                running_loss += loss.item() * inputs.size(0)
                running_corrects += torch.sum(preds == labels.data)

            if phase == 'train' and scheduler is not None:
                scheduler.step()

            epoch_loss = running_loss / dataset_sizes[phase]
            epoch_acc = running_corrects.double() / dataset_sizes[phase]

            print(f" [{phase.upper()}] Loss: {epoch_loss:.4f} | Acc: {epoch_acc:.4f} ({epoch_acc*100:.1f}%)")

            # Simpan bobot terbaik
            if phase == 'val' and epoch_acc > best_acc:
                best_acc = epoch_acc
                best_model_wts = copy.deepcopy(model.state_dict())

    time_elapsed = time.time() - since
    print(f"\n [OK] Training Selesai dalam {time_elapsed // 60:.0f}m {time_elapsed % 60:.0f}s")
    print(f" [OK] Akurasi Validasi Terbaik (Best Val Acc): {best_acc * 100:.2f}%")

    model.load_state_dict(best_model_wts)
    return model

# ---------------------------------------------------------
# 5. MAIN EXECUTION
# ---------------------------------------------------------
if __name__ == '__main__':
    print("=== TRAINING MODEL MOBILENETV3 CLASSIFICATION CABAI (3 KELAS KEMATANGAN) ===")
    
    dataloaders, dataset_sizes, class_names = load_data()
    print(f" -> Kelas Cabai ({len(class_names)}): {class_names}")
    print(f" -> Jumlah Sampel Train (80%): {dataset_sizes['train']} | Val (20%): {dataset_sizes['val']}")

    model = build_mobilenet_model(len(class_names))

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.AdamW(model.parameters(), lr=LEARNING_RATE, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=NUM_EPOCHS)

    print(" [*] Memulai Pelatihan Model MobileNetV3...")
    model = train_model(model, dataloaders, dataset_sizes, criterion, optimizer, scheduler, num_epochs=NUM_EPOCHS)

    # Simpan model ter-train ke model_cabe_mobilenet.pth
    torch.save(model.state_dict(), MODEL_SAVE_PATH)
    print(f"\n [SUCCESS] Model berhasil disimpan ke: {MODEL_SAVE_PATH}")
    print(f" [SUCCESS] Daftar kelas disimpan ke: {CLASS_SAVE_PATH}")
