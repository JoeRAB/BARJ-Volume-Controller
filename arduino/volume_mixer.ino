// BARJ Volume Controller — Arduino Sketch  (transmit-on-change, v2)
//
// Wire format (deej-compatible):  val0|val1|...|valN\n
//
// v2 note: each ADC channel is read twice and the first sample discarded.
// The ATmega's single ADC shares one sample-and-hold capacitor across all
// pins; reading channels back-to-back can make a weakly-connected or floating
// pin "ghost" the previous channel's value (e.g. slider 5 mirroring slider 4).
// The throwaway read lets the capacitor charge from the real source. Costs
// ~0.6 ms per cycle — negligible.

// ===========================================================================
//  CONFIGURATION  —  edit this section to match your wiring
// ===========================================================================
//
// 1. Set NUM_SLIDERS to how many potentiometers you have wired.
// 2. List the analog pin for each slider in SLIDER_PINS, in order.
//    Slider 1 is the first entry, slider 2 the second, and so on — this is
//    the order they appear (left to right) in the BARJ desktop app.
//
// Valid analog pins depend on your board:
//    Uno / Nano ........ A0 A1 A2 A3 A4 A5
//    Mega .............. A0 .. A15
//    Leonardo / Micro .. A0 A1 A2 A3 A4 A5 (plus A6–A11 on some pins)
//
// To remap a slider, just change its pin here and re-upload. To add or remove
// sliders, change NUM_SLIDERS and the list to match (they must be the same
// length), then re-upload.

const int NUM_SLIDERS = 5;

// One entry per slider, in app order (slider 1 first).
const int SLIDER_PINS[NUM_SLIDERS] = {
  A0,   // Slider 1
  A1,   // Slider 2
  A2,   // Slider 3
  A3,   // Slider 4
  A4,   // Slider 5
};

// --- Behaviour tuning (most people can leave these alone) ---
const int           DEADBAND     = 2;     // ignore jitter below ~0.2%
const unsigned long HEARTBEAT_MS = 500;   // max silence between sends (ms)
const int           LOOP_DELAY   = 10;    // ms between read cycles

// ===========================================================================
//  Implementation  —  no need to edit below here
// ===========================================================================

int analogSliderValues[NUM_SLIDERS];
int lastSentValues[NUM_SLIDERS];
unsigned long lastSendTime = 0;

void setup() {
  for (int i = 0; i < NUM_SLIDERS; i++) {
    pinMode(SLIDER_PINS[i], INPUT);
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

  delay(LOOP_DELAY);
}

void updateSliderValues() {
  for (int i = 0; i < NUM_SLIDERS; i++) {
    analogRead(SLIDER_PINS[i]);            // throwaway: settles the S&H cap
    delayMicroseconds(10);                 // brief settle on the new channel
    analogSliderValues[i] = analogRead(SLIDER_PINS[i]);   // real reading
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
