// BARJ Volume Controller — Arduino Sketch  (transmit-on-change, v2)
//
// v2: double-read each ADC channel and discard the first sample.
// The ATmega's single ADC shares one sample-and-hold capacitor across
// all pins; reading channels back-to-back can make a weakly-connected
// or floating pin "ghost" the previous channel's value (e.g. slider 5
// mirroring slider 4). The throwaway read gives the capacitor time to
// charge from the real source. Costs ~0.6 ms per cycle — negligible.
//
// Wire format unchanged (deej-compatible):  val0|val1|...|valN\n

const int NUM_SLIDERS = 5;
const int analogInputs[NUM_SLIDERS] = {A0, A1, A2, A3, A4};

const int DEADBAND = 2;                  // ignore jitter below ~0.2%
const unsigned long HEARTBEAT_MS = 500;  // max silence between sends

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
    analogRead(analogInputs[i]);            // throwaway: settles the S&H cap
    delayMicroseconds(10);                  // brief settle on the new channel
    analogSliderValues[i] = analogRead(analogInputs[i]);   // real reading
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
