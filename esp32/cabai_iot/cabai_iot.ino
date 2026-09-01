#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h> 
#include <DHT11.h> 

// =========================================================================
// 🌐 NETWORK SETTING: Kredensial Jaringan & Target IP Laptop Windows Anda
// =========================================================================
const char* WIFI_SSID     = "Padamu 2000 tahun mulai sekarang"; 
const char* WIFI_PASSWORD = "1sampai2";
const char* SERVER_URL    = "http://10.50.57.18:5001/api/sensor-data"; 

// =========================================================================
// 🔒 ALOKASI PIN FISIK ESP32 (LOCKED)
// =========================================================================
constexpr uint8_t DHT11_PIN  = 23;  
constexpr uint8_t SOIL_PIN   = 32;  
constexpr uint8_t RELAY_PIN  = 33;  

DHT11 dht11(DHT11_PIN); 

// =========================================================================
// ⚙️ PARAMETER KALIBRASI EMPIRIS TANAH DIRECT (Sesuai Karakteristik Fisik Anda)
// =========================================================================
constexpr int SAMPLE_COUNT = 30; 
constexpr unsigned long READ_INTERVAL_MS = 1500;

// Kalibrasi Aktual Sensor YL-69: ADC Tinggi (>= 2200) = KERING, ADC Rendah (<= 1400) = BASAH
constexpr int AMBANG_KERING = 2200; 
constexpr int AMBANG_BASAH  = 1400; 

int samples[SAMPLE_COUNT];

// =========================================================================
// 🛡️ PARAMETER LOGIKA POMPA & FAIL-SAFE TIMEOUT
// =========================================================================
constexpr uint8_t PUMP_ON   = HIGH; // Aktifkan penyiraman
constexpr uint8_t PUMP_OFF  = LOW;

constexpr unsigned long MAXIMUM_RUN_TIME_MS = 5000; // Maksimal siram 5 detik
constexpr unsigned long COOLDOWN_TIME_MS    = 15000; // Jeda 15 detik agar air meresap

unsigned long previousTelemetryMillis = 0;
unsigned long pumpStartTime = 0;
unsigned long cooldownStartTime = 0;

bool isPumpRunning = false;
bool isCoolingDown = false;

bool isAutoModeFromServer = true;
bool isOverrideOnFromServer = false;

// Nilai suhu, kelembapan, dan ADC tersimpan
float t_val = 28.0;
float h_val = 60.0;
int latestSoilRaw = 0;

// =========================================================================
// 🛠️ FUNGSI AKUISISI DATA SENSOR TANAH (MEDIAN FILTER - 100% ASLI ANDA)
// =========================================================================
int readSoilMedian() {
  pinMode(SOIL_PIN, INPUT);
  delay(50); // Jeda stabilisasi impedansi pin

  // Akuisisi Data Multisampling
  for (int i = 0; i < SAMPLE_COUNT; i++) {
    samples[i] = analogRead(SOIL_PIN);
    delay(15); 
  }

  // Algoritma Sorting (Bubble Sort Sederhana)
  for (int i = 0; i < SAMPLE_COUNT - 1; i++) {
    for (int j = i + 1; j < SAMPLE_COUNT; j++) {
      if (samples[j] < samples[i]) {
        int temp = samples[i];
        samples[i] = samples[j];
        samples[j] = temp;
      }
    }
  }

  // Ekstraksi Nilai Tengah (Median)
  return samples[SAMPLE_COUNT / 2];
}

// =========================================================================
// 🚀 INISIALISASI SISTEM (SETUP)
// =========================================================================
void setup() {
  Serial.begin(115200);
  delay(2000);

  // Inisialisasi & Kalibrasi Perangkat Keras ADC
  analogReadResolution(12);
  analogSetPinAttenuation(SOIL_PIN, ADC_11db);

  // Proteksi Awal Relay
  digitalWrite(RELAY_PIN, PUMP_OFF);
  pinMode(RELAY_PIN, OUTPUT);

  Serial.println(F("\n[JARINGAN] Menghubungkan ke Jaringan Hotspot..."));
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true);
  delay(100);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  int retryCount = 0;
  while (WiFi.status() != WL_CONNECTED) { 
    delay(500); 
    Serial.print(F(".")); 
    retryCount++;
    if (retryCount > 40) { // 20 detik tanpa koneksi -> reset Wi-Fi
      Serial.println(F("\n[JARINGAN] Retry menghubungkan ulang Wi-Fi..."));
      WiFi.disconnect(true);
      delay(200);
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
      retryCount = 0;
    }
  }
  Serial.println(F("\n[JARINGAN] TERHUBUNG KE LAPTOP SERVER LOKAL ✔️"));
  Serial.print(F("[JARINGAN] IP ESP32: "));
  Serial.println(WiFi.localIP());
}

// =========================================================================
// 🔄 EKSEKUSI LOGIKA UTAMA (LOOP - NON BLOCKING)
// =========================================================================
void loop() {
  unsigned long currentMillis = millis();

  // MANAJEMEN COOLDOWN: Cek apakah masa tunggu penyerapan 15 detik selesai
  if (isCoolingDown) {
    if (currentMillis - cooldownStartTime >= COOLDOWN_TIME_MS) {
      isCoolingDown = false;
      Serial.println(F("[SAFETY] Jeda penyerapan selesai. Otomatisasi kembali aktif."));
    }
  }

  // 1. JALUR TRANSMISI TELEMETRI BERKALA KE SERVER FLASK (Setiap 1.5 Detik)
  if (!isPumpRunning && (currentMillis - previousTelemetryMillis >= READ_INTERVAL_MS)) {
    previousTelemetryMillis = currentMillis;

    // Pembacaan DHT11 dibaca berkala setiap 1.5 detik agar bebas error
    int temperature = 0, humidity = 0;
    int resultDHT = dht11.readTemperatureHumidity(temperature, humidity);
    if (resultDHT == 0 && temperature > 0) {
      t_val = (float)temperature;
      h_val = (float)humidity;
    }

    // Membaca Nilai RAW ADC Sensor Tanah Menggunakan Median Filter
    int soilRaw = readSoilMedian();
    latestSoilRaw = soilRaw;
    String statusTanah = "";

    // EVALUASI LOGIKA KATEGORI: ADC Tinggi (>= 2200) = KERING, ADC Rendah (<= 1400) = BASAH
    if (soilRaw >= AMBANG_KERING) {
      statusTanah = F("KERING ⚠️");
    } 
    else if (soilRaw <= AMBANG_BASAH) {
      statusTanah = F("BASAH 💧");
    } 
    else {
      statusTanah = F("LEMBAP 👍 (Ideal)");
    }

    // Mapping Persentase untuk Dashboard Web (ADC Tinggi = 0% Kelembaban, ADC Rendah = 100%)
    float soilPercent = map(soilRaw, 4095, 1000, 0, 100);
    if (soilPercent < 0) soilPercent = 0;
    if (soilPercent > 100) soilPercent = 100;

    // Kirim Data Telemetri ke Server Flask
    if (WiFi.status() == WL_CONNECTED) {
      HTTPClient http;
      http.begin(SERVER_URL);
      http.addHeader("Content-Type", "application/json");

      JsonDocument doc;
      doc["temperature"]     = t_val;
      doc["humidity"]        = h_val;
      doc["soil_moisture"]   = soilPercent;
      doc["light_intensity"] = 0.0; 
      doc["pump_status"]     = isPumpRunning;

      String requestBody;
      serializeJson(doc, requestBody);
      int httpCode = http.POST(requestBody);

      if (httpCode == 200) {
        String response = http.getString();
        JsonDocument resDoc;
        deserializeJson(resDoc, response);
        
        isAutoModeFromServer   = resDoc["controls"]["auto_mode"];
        isOverrideOnFromServer  = resDoc["controls"]["pump_override"];
      }
      http.end();
    }

    // Output Telemetri untuk Serial Monitor Lokal (Format Asli Anda)
    Serial.print(F("Soil Median ADC : "));
    Serial.print(soilRaw);
    Serial.print(F(" -> "));
    Serial.println(statusTanah);
    Serial.println(F("----------------------------------------"));
  }

  // =====================================================================
  // 🧠 LOGIKA EKSEKUSI PEMICU POMPA (RESPON LANGSUNG DARI WEB DASHBOARD)
  // =====================================================================
  if (isOverrideOnFromServer) {
    // PRIORITAS 1: Perintah Manual ON dari Klik Tombol Web Dashboard
    if (!isPumpRunning) {
      digitalWrite(RELAY_PIN, PUMP_ON);
      pumpStartTime = millis();
      isPumpRunning = true;
      Serial.println(F("[MANUAL] Klik Tombol Web ON -> Pompa HIDUP! 💧"));
    }
  } 
  else if (isAutoModeFromServer) {
    // PRIORITAS 2: Mode Otomatis (Tanah Kering ADC >= 2200 & tidak dalam cooldown)
    if (!isCoolingDown && latestSoilRaw >= AMBANG_KERING && !isPumpRunning) {
      digitalWrite(RELAY_PIN, PUMP_ON);
      pumpStartTime = millis();
      isPumpRunning = true;
      Serial.println(F("[AUTO] Deteksi Tanah Kering (ADC >= 2200) -> Pompa HIDUP! 💧"));
    }
  } 
  else {
    // PRIORITAS 3: Perintah Manual OFF / Standby
    if (isPumpRunning) {
      digitalWrite(RELAY_PIN, PUMP_OFF);
      isPumpRunning = false;
      Serial.println(F("[MANUAL] Perintah Web OFF -> Pompa MATI! 🔒"));
    }
  }

  // =====================================================================
  // 🛡️ PROTEKSI FAIL-SAFE (HARD TIMEOUT PENYIRAMAN MAKSIMAL 5 DETIK)
  // =====================================================================
  if (isPumpRunning) {
    if (currentMillis - pumpStartTime >= MAXIMUM_RUN_TIME_MS) {
      digitalWrite(RELAY_PIN, PUMP_OFF);
      isPumpRunning = false;
      isOverrideOnFromServer = false;
      
      // Kunci sistem ke masa cooldown 15 detik agar air meresap
      isCoolingDown = true;
      cooldownStartTime = millis();
      
      Serial.println(F("[SAFETY] Batas aman 5 detik habis! Pompa diputus paksa."));
      Serial.println(F("[SAFETY] Sistem dikunci 15 detik agar air meresap ke tanah..."));
      previousTelemetryMillis = millis(); 
    }
  }
}
