#include <DHT.h>
#include <Adafruit_BMP280.h>
#include <Wire.h>
#include <ArduinoJson.h>

// ================= DHT11 =================
#define DHT_PIN 4
#define DHT_TYPE DHT11
DHT dht(DHT_PIN, DHT_TYPE);

// ================= BMP280 =================
#define BMP_SDA 21
#define BMP_SCL 22
Adafruit_BMP280 bmp;
bool bmpOk = false;

// ================= RAIN =================
#define RAIN_PIN 34
#define RAIN_THRESHOLD 1500

// ================= TIMING =================
unsigned long lastSend = 0;
#define INTERVAL 2000

// ================= SETUP =================
void setup() {
  Serial.begin(115200);
  delay(2000); // stabilize boot

  dht.begin();
  delay(1000);

  Wire.begin(BMP_SDA, BMP_SCL);

  bmpOk = bmp.begin(0x76);
  if (!bmpOk) bmpOk = bmp.begin(0x77);

  Serial.println("WeatherSense ESP32 Stable Mode Started");
}

// ================= SAFE READ =================
float getTemp() {
  float t = dht.readTemperature();
  return isnan(t) ? -999 : t;
}

float getHumidity() {
  float h = dht.readHumidity();
  return isnan(h) ? -999 : h;
}

float getPressure() {
  if (!bmpOk) return 1008.0;

  float p = bmp.readPressure();
  return isnan(p) ? 1008.0 : (p / 100.0f);
}

bool getRain() {
  int val = analogRead(RAIN_PIN);

  if (val < 0 || val > 4095) return false;

  return val < RAIN_THRESHOLD;
}

// ================= LOOP =================
void loop() {

  delay(10);  // 🔥 watchdog safety

  if (millis() - lastSend < INTERVAL) return;
  lastSend = millis();

  float temp = getTemp();
  float hum = getHumidity();
  float pressure = getPressure();
  bool rain = getRain();

  // ================= JSON OUTPUT (IMPORTANT FIX) =================
  StaticJsonDocument<256> doc;

  doc["temperature"] = temp;
  doc["humidity"] = hum;
  doc["pressure"] = pressure;
  doc["rain"] = rain;

  serializeJson(doc, Serial);
  Serial.println();   // 🔥 MUST be single line JSON

}



/*

#include <WiFi.h>
#include <HTTPClient.h>
#include <DHT.h>
#include <Adafruit_BMP280.h>
#include <ArduinoJson.h>
#include <time.h>
#include <Wire.h>

// ============ CONFIG ============
#define WIFI_SSID       "sadman"
#define WIFI_PASSWORD   "sadman12"
#define SERVER_URL      "http://10.88.7.106:5000/api/sensor"  //10.111.121.106

#define POST_INTERVAL_MS 2000 // Time Delay

// ============ DHT ============
#define DHT_TYPE DHT11
#define DHT_PIN 4
DHT dht(DHT_PIN, DHT_TYPE);

// ============ BMP280 ============
#define BMP_SDA 21
#define BMP_SCL 22
Adafruit_BMP280 bmp;
bool bmpOk = false;

// ============ RAIN ============
#define RAIN_PIN 34
#define RAIN_THRESHOLD 1500

// ============ TIMING ============
unsigned long lastPost = 0;

// ============ SETUP ============
void setup() {
  Serial.begin(115200);
  delay(500);

  dht.begin();

  Wire.begin(BMP_SDA, BMP_SCL);
  bmpOk = bmp.begin(0x76);
  if (!bmpOk) bmpOk = bmp.begin(0x77);

  connectWiFi();
  configTime(0, 0, "pool.ntp.org");
}

// ============ LOOP ============
void loop() {
  if (WiFi.status() != WL_CONNECTED)
    connectWiFi();

  if (millis() - lastPost >= POST_INTERVAL_MS) {
    lastPost = millis();
    sendData();
  }

  delay(1000);
}

// ============ WIFI ============
void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int t = 0;
  while (WiFi.status() != WL_CONNECTED && t < 30) {
    delay(500);
    t++;
  }

  // 🔥 ADDED: PRINT IP ADDRESS
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("WiFi Connected");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("WiFi Connection Failed");
  }
}

// ============ SENSOR READ ============
float readTemp() {
  float t = dht.readTemperature();
  return isnan(t) ? -999 : t;
}

float readHumidity() {
  float h = dht.readHumidity();
  return isnan(h) ? -999 : h;
}

float readPressure() {
  if (!bmpOk) return 1008.0;
  return bmp.readPressure() / 100.0f;
}

bool readRain() {
  return analogRead(RAIN_PIN) < RAIN_THRESHOLD;
}

// ============ TIME ============
String getTimestamp() {
  struct tm t;
  if (!getLocalTime(&t, 5000))
    return "1970-01-01T00:00:00Z";

  char buf[25];
  strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &t);
  return String(buf);
}

// ============ SEND ============
void sendData() {

  float temp = readTemp();
  float hum = readHumidity();
  float pressure = readPressure();
  bool rain = readRain();

  // SERIAL OUTPUT
  Serial.println("------ SENSOR DATA ------");
  Serial.print("Temperature: "); Serial.print(temp); Serial.println(" °C");
  Serial.print("Humidity: "); Serial.print(hum); Serial.println(" %");
  Serial.print("Pressure: "); Serial.print(pressure); Serial.println(" hPa");
  Serial.print("Rain: "); Serial.println(rain ? "YES" : "NO");
  Serial.print("BMP280 Status: "); Serial.println(bmpOk ? "WORKING" : "NOT WORKING");
  Serial.println("-------------------------");

  StaticJsonDocument<256> doc;

  doc["timestamp"] = getTimestamp();
  doc["temperature"] = round(temp * 10) / 10.0;
  doc["humidity"] = round(hum * 10) / 10.0;
  doc["pressure"] = round(pressure * 10) / 10.0;
  doc["rain"] = rain;

  char buffer[256];
  serializeJson(doc, buffer);

  sendHTTP(buffer);
}

// ============ HTTP ============
void sendHTTP(const char* json) {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");

  http.POST((uint8_t*)json, strlen(json));
  http.end();
}

*/