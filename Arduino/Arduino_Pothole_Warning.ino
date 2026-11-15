#include <Wire.h>
#include <Arduino_LSM6DS3.h>
#include <LiquidCrystal_I2C.h>
#include <math.h>

// ==========================================
// PIN CONFIGURATION
// ==========================================

#define RED_LED 4
#define GREEN_LED 5
#define BUZZER 6

// ==========================================
// LCD
// ==========================================

LiquidCrystal_I2C lcd(0x27, 16, 2);

// ==========================================
// SENSOR VARIABLES
// ==========================================

float x, y, z;
float gx, gy, gz;

float accelMagnitude = 0;
float gyroMagnitude = 0;

float baseline = 1.0;

// ==========================================
// DETECTION SETTINGS
// ==========================================

const float POTHOLE_THRESHOLD = 0.22;

const float SPEED_BUMP_TRIGGER = 0.07;
const float SPEED_BUMP_THRESHOLD = 0.12;

const float GYRO_THRESHOLD = 100.0;

const unsigned long EVENT_WINDOW = 900;
const unsigned long EVENT_COOLDOWN = 1500;

const unsigned long SPEED_BUMP_RECOVERY = 700;

// ==========================================
// EVENT VARIABLES
// ==========================================

bool detecting = false;

unsigned long eventStart = 0;
unsigned long lastAlert = 0;
unsigned long recoveryUntil = 0;

float peakImpact = 0;
float peakGyro = 0;

int impactPeaks = 0;

float previousImpact = 0;

bool rising = false;

// ==========================================
// ADVANCE WARNING VARIABLES
// ==========================================

bool warningActive = false;

String warningType = "";
String warningLevel = "";

int warningDistance = 0; // Distance received from Pi, in centimetres

unsigned long lastWarningBeep = 0;

unsigned long warningInterval = 0;

bool warningBuzzerState = false;

// ==========================================
// SERIAL COMMAND BUFFER
// ==========================================

String serialBuffer = "";

// ==========================================
// SETUP
// ==========================================

void setup() {

  Serial.begin(115200);

  pinMode(RED_LED, OUTPUT);
  pinMode(GREEN_LED, OUTPUT);
  pinMode(BUZZER, OUTPUT);

  digitalWrite(RED_LED, LOW);
  digitalWrite(GREEN_LED, HIGH);
  digitalWrite(BUZZER, LOW);

  Wire.begin();

  lcd.init();
  lcd.backlight();

  lcd.setCursor(0, 0);
  lcd.print("Road Detection");

  lcd.setCursor(0, 1);
  lcd.print("Initializing...");

  if (!IMU.begin()) {

    lcd.clear();
    lcd.print("IMU ERROR!");

    Serial.println("IMU_ERROR");

    while (1);
  }

  delay(1500);

  // ========================================
  // CALIBRATION
  // ========================================

  lcd.clear();
  lcd.print("Calibrating...");

  float total = 0;
  int samples = 0;

  unsigned long start = millis();

  while (millis() - start < 3000) {

    if (IMU.accelerationAvailable()) {

      IMU.readAcceleration(x, y, z);

      float magnitude =
        sqrt(x * x + y * y + z * z);

      total += magnitude;
      samples++;
    }
  }

  if (samples > 0) {

    baseline = total / samples;
  }

  lcd.clear();
  lcd.print("System Ready");

  Serial.println("SYSTEM_READY");

  Serial.print("Baseline:");
  Serial.println(baseline, 3);

  delay(1500);
}

// ==========================================
// MAIN LOOP
// ==========================================

void loop() {

  // Always check Raspberry Pi commands
  readSerialCommands();

  // Update advance warning system
  updateWarningSystem();

  // Read IMU only when data is available
  if (!IMU.accelerationAvailable()) {
    return;
  }

  IMU.readAcceleration(x, y, z);

  accelMagnitude =
    sqrt(x * x + y * y + z * z);

  if (IMU.gyroscopeAvailable()) {

    IMU.readGyroscope(gx, gy, gz);

    gyroMagnitude =
      sqrt(gx * gx + gy * gy + gz * gz);
  }

  float impact =
    abs(accelMagnitude - baseline);

  unsigned long currentTime = millis();

  // ========================================
  // EVENT START
  // ========================================

  if (!detecting &&
      currentTime >= recoveryUntil &&
      impact >= SPEED_BUMP_TRIGGER) {

    detecting = true;

    eventStart = currentTime;

    peakImpact = impact;
    peakGyro = gyroMagnitude;

    impactPeaks = 0;

    previousImpact = impact;

    rising = true;
  }

  // ========================================
  // TRACK EVENT
  // ========================================

  if (detecting) {

    if (impact > peakImpact) {
      peakImpact = impact;
    }

    if (gyroMagnitude > peakGyro) {
      peakGyro = gyroMagnitude;
    }

    if (rising &&
        impact < previousImpact &&
        previousImpact >= SPEED_BUMP_TRIGGER) {

      impactPeaks++;

      rising = false;
    }

    if (impact > previousImpact) {
      rising = true;
    }

    previousImpact = impact;

    unsigned long duration =
      currentTime - eventStart;

    // ======================================
    // FINISH EVENT
    // ======================================

    if (duration >= EVENT_WINDOW) {

      detecting = false;

      classifyEvent(duration);

      resetDetection();
    }
  }

  // ========================================
  // NORMAL DISPLAY
  // ========================================

  if (!detecting && !warningActive) {

    lcd.setCursor(0, 0);
    lcd.print("Road: Normal    ");

    lcd.setCursor(0, 1);
    lcd.print("Impact:");
    lcd.print(impact, 2);
    lcd.print("   ");

    digitalWrite(GREEN_LED, HIGH);
    digitalWrite(RED_LED, LOW);
  }

  // ========================================
  // SERIAL DEBUGGING
  // ========================================

  Serial.print("ACC:");
  Serial.print(accelMagnitude, 3);

  Serial.print(",GYRO:");
  Serial.print(gyroMagnitude, 2);

  Serial.print(",IMPACT:");
  Serial.print(impact, 3);

  Serial.print(",PEAK:");
  Serial.print(peakImpact, 3);

  Serial.print(",PEAKS:");
  Serial.println(impactPeaks);
}

// ==========================================
// READ COMMANDS FROM RASPBERRY PI
// ==========================================

void readSerialCommands() {

  while (Serial.available()) {

    char incoming = Serial.read();

    if (incoming == '\n') {

      serialBuffer.trim();

      if (serialBuffer.length() > 0) {

        processCommand(serialBuffer);
      }

      serialBuffer = "";
    }

    else if (incoming != '\r') {

      if (serialBuffer.length() < 100) {

        serialBuffer += incoming;
      }
      else {

        serialBuffer = "";
      }
    }
  }
}

// ==========================================
// PROCESS RASPBERRY PI COMMANDS
// ==========================================

void processCommand(String command) {

  // ========================================
  // CLEAR WARNING
  // ========================================

  if (command == "CLEAR") {

    warningActive = false;

    warningType = "";
    warningLevel = "";

    warningDistance = 0;

    warningBuzzerState = false;

    noTone(BUZZER);

    digitalWrite(RED_LED, LOW);
    digitalWrite(GREEN_LED, HIGH);

    lcd.clear();

    lcd.setCursor(0, 0);
    lcd.print("Road: Normal");

    Serial.println("WARNING_CLEARED");

    return;
  }

  // ========================================
  // WARNING COMMAND
  // FORMAT:
  // WARNING:POTHOLE,150,AHEAD
  // ========================================

  if (command.startsWith("WARNING:")) {

    command.remove(0, 8);

    int firstComma = command.indexOf(',');

    int secondComma = command.indexOf(
      ',',
      firstComma + 1
    );

    if (firstComma == -1 ||
        secondComma == -1) {

      Serial.println("INVALID_WARNING_COMMAND");

      return;
    }

    warningType = command.substring(
      0,
      firstComma
    );

    warningDistance = command.substring(
      firstComma + 1,
      secondComma
    ).toInt();

    warningLevel = command.substring(
      secondComma + 1
    );

    if (warningType != "POTHOLE" &&
        warningType != "SPEED_BUMP") {

      Serial.println("INVALID_HAZARD_TYPE");

      return;
    }

    warningActive = true;

    warningBuzzerState = false;

    lastWarningBeep = 0;

    noTone(BUZZER);

    displayWarning();

    Serial.println("WARNING_RECEIVED");
  }
}

// ==========================================
// DISPLAY WARNING ON LCD
// ==========================================

void displayWarning() {

  lcd.clear();

  if (warningType == "POTHOLE") {
    lcd.setCursor(0, 0);
    lcd.print("POTHOLE AHEAD!");
  }
  else {
    lcd.setCursor(0, 0);
    lcd.print("SPEED BUMP!");
  }

  lcd.setCursor(0, 1);

  if (warningDistance <= 0) {
    lcd.print("REACHED!");
  }
  else {
    lcd.print(warningDistance);
    lcd.print("cm ");
    lcd.print(warningLevel);
  }
}

// ==========================================
// ADVANCE WARNING SYSTEM (DISTANCES IN CM)
// ==========================================

void updateWarningSystem() {

  if (!warningActive) {
    return;
  }

  unsigned long currentTime = millis();

  // 0 cm = reached; 1-50 cm = danger;
  // 51-100 cm = caution; above 100 cm = ahead.

  if (warningDistance <= 0) {
    warningInterval = 150;
    digitalWrite(RED_LED, HIGH);
    digitalWrite(GREEN_LED, LOW);
  }
  else if (warningDistance <= 50) {
    warningInterval = 250;
    digitalWrite(RED_LED, HIGH);
    digitalWrite(GREEN_LED, LOW);
  }
  else if (warningDistance <= 100) {
    warningInterval = 600;
    digitalWrite(RED_LED, HIGH);
    digitalWrite(GREEN_LED, LOW);
  }
  else {
    warningInterval = 1200;
    digitalWrite(RED_LED, HIGH);
    digitalWrite(GREEN_LED, LOW);
  }

  // Non-blocking buzzer pattern.
  if (currentTime - lastWarningBeep >= warningInterval) {

    lastWarningBeep = currentTime;
    warningBuzzerState = !warningBuzzerState;

    if (warningBuzzerState) {

      if (warningDistance <= 0) {
        tone(BUZZER, 2200);
      }
      else if (warningDistance <= 50) {
        tone(BUZZER, 1800);
      }
      else if (warningDistance <= 100) {
        tone(BUZZER, 1300);
      }
      else {
        tone(BUZZER, 900);
      }
    }
    else {
      noTone(BUZZER);
    }
  }
}

// ==========================================
// EVENT CLASSIFICATION
// ==========================================

void classifyEvent(unsigned long duration) {

  unsigned long currentTime = millis();

  if (currentTime - lastAlert < EVENT_COOLDOWN) {
    return;
  }

  String eventType = "";

  // ========================================
  // POTHOLE DETECTION
  // ========================================

  if (peakImpact >= POTHOLE_THRESHOLD &&
      (peakGyro >= GYRO_THRESHOLD ||
       peakImpact >= 0.30)) {

    eventType = "POTHOLE";
  }

  // ========================================
  // SPEED BUMP DETECTION
  // ========================================

  else if (peakImpact >= SPEED_BUMP_THRESHOLD) {

    eventType = "SPEED_BUMP";
  }

  else {

    return;
  }

  lastAlert = currentTime;

  // ========================================
  // LOCAL POTHOLE ALERT
  // ========================================

  if (eventType == "POTHOLE") {

    digitalWrite(RED_LED, HIGH);
    digitalWrite(GREEN_LED, LOW);

    tone(BUZZER, 1500, 500);

    lcd.clear();

    lcd.setCursor(0, 0);
    lcd.print("POTHOLE ALERT!");

    lcd.setCursor(0, 1);
    lcd.print("Impact:");
    lcd.print(peakImpact, 2);
  }

  // ========================================
  // LOCAL SPEED BUMP ALERT
  // ========================================

  else {

    digitalWrite(RED_LED, LOW);
    digitalWrite(GREEN_LED, HIGH);

    tone(BUZZER, 900, 300);

    lcd.clear();

    lcd.setCursor(0, 0);
    lcd.print("SPEED BUMP!");

    lcd.setCursor(0, 1);
    lcd.print("Slow Down!");

    recoveryUntil =
      millis() + SPEED_BUMP_RECOVERY;

    Serial.println("SPEED_BUMP_RECOVERY_STARTED");
  }

  // ========================================
  // SEND EVENT TO RASPBERRY PI
  // ========================================

  Serial.print("EVENT:");
  Serial.print(eventType);

  Serial.print(",Impact:");
  Serial.print(peakImpact, 3);

  Serial.print(",Gyro:");
  Serial.print(peakGyro, 2);

  Serial.print(",Peaks:");
  Serial.print(impactPeaks);

  Serial.print(",Duration:");
  Serial.println(duration);

  delay(400);

  noTone(BUZZER);

  digitalWrite(RED_LED, LOW);
  digitalWrite(GREEN_LED, HIGH);

  if (!warningActive) {

    lcd.clear();
    lcd.print("Road: Normal");
  }
}

// ==========================================
// RESET DETECTION
// ==========================================

void resetDetection() {

  detecting = false;

  peakImpact = 0;
  peakGyro = 0;

  impactPeaks = 0;

  previousImpact = 0;

  rising = false;
}
