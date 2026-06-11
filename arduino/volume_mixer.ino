// BARJ Volume Controller — Arduino Sketch  (transmit-on-change edition)
//
// Wire format is unchanged (deej-compatible):  val0|val1|...|valN\n
// so NO changes are needed on the PC side.
//
// Efficiency: instead of transmitting ~38 messages/sec forever, this
// version only transmits when a pot actually moves beyond a small
// deadband, plus a heartbeat every 500 ms so the app still receives
// regular data (used for smoothing convergence and disconnect detection).
// Idle serial traffic drops by ~95%.
//
// Wiring per potentiometer:
//   Left pin  (GND)   -> Arduino GND
//   Middle    (wiper) -> A0, A1, A2, A3, A4
//   Right pin (5V)    -> Arduino 5V

const int NUM_SLIDERS = 5;
const int analogInputs[NUM_SLIDERS] = {A0, A1, A2, A3, A4};

// Ignore jitter below this many ADC counts (1023 counts = full travel).
// 2 counts ≈ 0.2% — below what the app displays, so nothing is lost.
const int DEADBAND = 2;

// Maximum silence between transmissions. The PC app uses incoming data
// for smoothing convergence; 500 ms keeps that responsive while idle.
const unsigned long HEARTBEAT_MS = 500;

int analogSliderValues[NUM_SLIDERS];
int lastSentValues[NUM_SLIDERS];
unsigned long lastSendTime = 0;

void setup() {
  for (int i = 0; i < NUM_SLIDERS; i++) {
    pinMode(analogInputs[i], INPUT);
    lastSentValues[i] = -1000;   // force a send on first loop
  }
  Serial.begin(9600);
}

void loop() {
  updateSliderValues();

  // Did any pot move beyond the deadband since the last transmission?
  bool changed = false;
  for (int i = 0; i < NUM_SLIDERS; i++) {
    if (abs(analogSliderValues[i] - lastSentValues[i]) > DEADBAND) {
      changed = true;
      break;
    }
  }

  unsigned long now = millis();
  if (changed || (now - lastSendTime) >= HEARTBEAT_MS) {
    sendSliderValues();
    for (int i = 0; i < NUM_SLIDERS; i++) {
      lastSentValues[i] = analogSliderValues[i];
    }
    lastSendTime = now;
  }

  delay(10);
}

void updateSliderValues() {
  for (int i = 0; i < NUM_SLIDERS; i++) {
    analogSliderValues[i] = analogRead(analogInputs[i]);
  }
}

void sendSliderValues() {
  String builtString = String("");
  for (int i = 0; i < NUM_SLIDERS; i++) {
    builtString += String((int)analogSliderValues[i]);
    if (i < NUM_SLIDERS - 1) {
      builtString += String("|");
    }
  }
  Serial.println(builtString);
}
