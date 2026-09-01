#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include "esp_http_server.h"

// =========================================================================
// 🌐 KREDENSIAL WIFI & IP LAPTOP SERVER
// =========================================================================
const char *ssid     = "Padamu 2000 tahun mulai sekarang";
const char *password = "1sampai2";

// IP Laptop Server Flask Anda (Port 5001)
const char *flaskServerIP = "10.50.57.18";

// =========================================================================
// 🔒 ESP32 WROVER CAMERA PINOUT DEFINITION (LOCKED)
// =========================================================================
#define PWDN_GPIO_NUM     -1
#define RESET_GPIO_NUM    -1

#define XCLK_GPIO_NUM      21
#define SIOD_GPIO_NUM      26
#define SIOC_GPIO_NUM      27

#define Y9_GPIO_NUM        35
#define Y8_GPIO_NUM        34
#define Y7_GPIO_NUM        39
#define Y6_GPIO_NUM        36

#define Y5_GPIO_NUM        19
#define Y4_GPIO_NUM        18
#define Y3_GPIO_NUM         5
#define Y2_GPIO_NUM        4

#define VSYNC_GPIO_NUM     25
#define HREF_GPIO_NUM      23
#define PCLK_GPIO_NUM      22

httpd_handle_t stream_httpd = NULL;

#define PART_BOUNDARY "123456789000000000000987654321"
static const char* _STREAM_CONTENT_TYPE = "multipart/x-mixed-replace; boundary=" PART_BOUNDARY;
static const char* _STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* _STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

// =========================================================================
// 📹 MJPEG STREAM HANDLER (25-30 FPS TANPA LAG / ZERO OVERHEAD)
// =========================================================================
static esp_err_t stream_handler(httpd_req_t *req) {
  camera_fb_t * fb = NULL;
  esp_err_t res = ESP_OK;
  size_t _jpg_buf_len = 0;
  uint8_t * _jpg_buf = NULL;
  char part_buf[64];

  res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
  if (res != ESP_OK) {
    return res;
  }

  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

  while (true) {
    fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("❌ Camera capture failed");
      res = ESP_FAIL;
    } else {
      _jpg_buf_len = fb->len;
      _jpg_buf = fb->buf;
    }

    if (res == ESP_OK) {
      size_t hlen = snprintf(part_buf, 64, _STREAM_PART, _jpg_buf_len);
      res = httpd_resp_send_chunk(req, part_buf, hlen);
    }
    if (res == ESP_OK) {
      res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);
    }
    if (res == ESP_OK) {
      res = httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY));
    }

    if (fb) {
      esp_camera_fb_return(fb);
      fb = NULL;
      _jpg_buf = NULL;
    } else {
      break;
    }

    if (res != ESP_OK) {
      break;
    }
  }
  return res;
}

// =========================================================================
// 📷 SINGLE CAPTURE HANDLER FOR AI SNAPSHOT (/capture)
// =========================================================================
static esp_err_t capture_handler(httpd_req_t *req) {
  camera_fb_t * fb = esp_camera_fb_get();
  if (fb) {
    esp_camera_fb_return(fb); // Flush buffer lama
  }
  fb = esp_camera_fb_get();

  if (!fb) {
    httpd_resp_send_500(req);
    return ESP_FAIL;
  }

  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Content-Disposition", "inline; filename=capture.jpg");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

  esp_err_t res = httpd_resp_send(req, (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  return res;
}

// =========================================================================
// 🌐 START NATIVE ESP32 HTTP STREAM SERVER (PORT 80)
// =========================================================================
void startCameraServer() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 80;

  httpd_uri_t stream_uri = {
    .uri       = "/stream",
    .method    = HTTP_GET,
    .handler   = stream_handler,
    .user_ctx  = NULL
  };

  httpd_uri_t capture_uri = {
    .uri       = "/capture",
    .method    = HTTP_GET,
    .handler   = capture_handler,
    .user_ctx  = NULL
  };

  if (httpd_start(&stream_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(stream_httpd, &stream_uri);
    httpd_register_uri_handler(stream_httpd, &capture_uri);
    Serial.println("✅ MJPEG Camera Stream Server Started on Port 80!");
  }
}

// =========================================================================
// 📷 INITIALIZE CAMERA & FIX ORIENTATION (VFLIP + HMIRROR)
// =========================================================================
void startCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;

  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;

  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;

  config.xclk_freq_hz = 20000000; // 20MHz untuk stream sangat lancar
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size   = FRAMESIZE_VGA; // 640x480 (atau FRAMESIZE_QVGA untuk super fast)
  config.jpeg_quality = 12;
  config.fb_count     = 2;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("❌ Camera init failed 0x%x\n", err);
    while (true) { delay(1000); }
  }

  // ORIENTASI HARDWARE: Membalik vertikal & cermin horizontal
  sensor_t *s = esp_camera_sensor_get();
  if (s != NULL) {
    s->set_vflip(s, 1);    // 1 = Balik atas-bawah
    s->set_hmirror(s, 1);  // 1 = Cermin kiri-kanan
  }

  Serial.println("✅ Camera Hardware Configured!");
}

// =========================================================================
// 📶 WIFI CONNECT & ANNOUNCE IP TO FLASK BACKEND
// =========================================================================
void connectWiFi() {
  Serial.print("Connecting WiFi: ");
  Serial.println(ssid);

  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true);
  delay(100);
  WiFi.setAutoReconnect(true);
  WiFi.begin(ssid, password);

  int retryCount = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    retryCount++;
    if (retryCount > 40) {
      Serial.println("\n[WiFi] Retry reconnecting...");
      WiFi.disconnect(true);
      delay(200);
      WiFi.begin(ssid, password);
      retryCount = 0;
    }
  }

  Serial.println("\n✅ WiFi Connected!");
  Serial.print("🎥 ESP32-CAM Stream URL: http://");
  Serial.print(WiFi.localIP());
  Serial.println("/stream");

  // Pengumuman IP ke Server Flask
  HTTPClient http;
  String announceURL = "http://" + String(flaskServerIP) + ":5001/api/camera/announce?ip=" + WiFi.localIP().toString();
  http.begin(announceURL);
  int code = http.GET();
  if (code > 0) {
    Serial.printf("📢 Announced IP to Flask Server: %s\n", WiFi.localIP().toString().c_str());
  }
  http.end();
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n=== ESP32-CAM MJPEG STREAM SERVER (25-30 FPS) ===");

  startCamera();
  connectWiFi();
  startCameraServer();
}

void loop() {
  // Server MJPEG streaming berjalan otomatis secara async di background task!
  delay(10000);
}