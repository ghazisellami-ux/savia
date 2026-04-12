/*
 * 🏥 SIC RADIOLOGIE - Wireless Sensor Node (ESP32)
 * 
 * Connecting Medical IoT to the Dashboard via MQTT.
 * 
 * HARDWARE:
 * - ESP32 DevKit V1
 * - DHT22 (Temp/Hum) connected to GPIO 4
 * - MPU6050 (Vibration) connected to I2C (GPIO 21 SDA, GPIO 22 SCL)
 * 
 * LIBRARIES NEEDED (Install via Library Manager):
 * - "PubSubClient" by Nick O'Leary
 * - "DHT sensor library" by Adafruit
 * - "Adafruit MPU6050" by Adafruit
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Wire.h>

// =================CONFIG=================
const char* ssid = "NOM_DU_WIFI_CLINIQUE";
const char* password = "MOT_DE_PASSE_WIFI";
const char* mqtt_server = "192.168.1.100"; // IP du PC où tourne SIC Radiologie
const int mqtt_port = 1883;

#define MACHINE_ID "IRM-01"  // Changer pour chaque ESP32 (SCANNER-02, RADIO-03...)
// ========================================

// Pins
#define DHTPIN 4
#define DHTTYPE DHT22

WiFiClient espClient;
PubSubClient client(espClient);
DHT dht(DHTPIN, DHTTYPE);
Adafruit_MPU6050 mpu;

unsigned long lastMsg = 0;
#define MSG_INTERVAL 5000 // Envoyer toutes les 5 secondes

void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Connecting to ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("");
  Serial.println("WiFi connected");
  Serial.println("IP address: ");
  Serial.println(WiFi.localIP());
}

void callback(char* topic, byte* message, unsigned int length) {
  // Pas besoin de recevoir des messages pour l'instant
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    if (client.connect(MACHINE_ID)) {
      Serial.println("connected");
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  setup_wifi();
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);

  // Init DHT
  dht.begin();

  // Init MPU6050
  if (!mpu.begin()) {
    Serial.println("Failed to find MPU6050 chip");
  } else {
    mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
  }
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  unsigned long now = millis();
  if (now - lastMsg > MSG_INTERVAL) {
    lastMsg = now;

    // 1. Lire Température
    float temp = dht.readTemperature();
    if (!isnan(temp)) {
      String msg = "{\"machine\": \"" + String(MACHINE_ID) + "\", \"sensor\": \"TEMP\", \"value\": " + String(temp) + "}";
      client.publish("sic/telemetry/temp", msg.c_str());
      Serial.println(msg);
    }

    // 2. Lire Vibration (Accélération Totale)
    sensors_event_t a, g, temp_mpu;
    mpu.getEvent(&a, &g, &temp_mpu);
    
    // Magnitude du vecteur accélération (en G/m/s^2) - Gravité (approx 9.8)
    // On simplifie en envoyant juste la variation max sur X
    float vib = abs(a.acceleration.x); 
    
    String msgVib = "{\"machine\": \"" + String(MACHINE_ID) + "\", \"sensor\": \"VIBRATION\", \"value\": " + String(vib) + "}";
    client.publish("sic/telemetry/vib", msgVib.c_str());
    Serial.println(msgVib);
  }
}
