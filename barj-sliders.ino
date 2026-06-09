/*
 * BARJ Volume Controller - Arduino Firmware
 * Target board: SparkFun Pro Micro / Arduino Leonardo (ATmega32U4)
 *
 * Protocol (backward-compatible with deej, plus a BARJ handshake):
 *   - Continuously streams analog slider values as pipe-separated integers
 *     terminated by newline, e.g.:  0|512|1023|240|768\n
 *     (each value 0..1023, one per configured slider)
 *
 *   - Handshake / control commands (sent by the PC client, newline-terminated):
 *       "barj-id?"   -> replies one line: "BARJ|<fwVersion>|<numSliders>\n"
 *                       Used by the GUI to auto-identify BARJ devices and
 *                       discover how many sliders this unit reports.
 *       "barj-ping"  -> replies "BARJ|pong\n"
 *
 * Notes:
 *   - Pro Micro analog pins: A0(18) A1(19) A2(20) A3(21) and A6/A8/A9/A10 etc.
 *     The safe, commonly-broken-out analog pins are A0..A3 plus A6..A10.
 *   - Edit NUM_SLIDERS and SLIDER_PINS below to match your hardware.
 *     The PC GUI can read more or fewer sliders than exist, but for best
 *     results keep NUM_SLIDERS equal to your physical slider count.
 */

#define FW_VERSION "1.0.0"

// ---- Configuration ---------------------------------------------------------
const int NUM_SLIDERS = 5;                                  // change to match your build
const int SLIDER_PINS[NUM_SLIDERS] = { A0, A1, A2, A3, A6 }; // Pro Micro analog pins

const unsigned long BAUD_RATE      = 9600;
const unsigned long SEND_INTERVAL  = 10;   // ms between value frames (~100 Hz)
// ----------------------------------------------------------------------------

int analogSliderValues[NUM_SLIDERS];
unsigned long lastSend = 0;

void setup() {
  for (int i = 0; i < NUM_SLIDERS; i++) {
    pinMode(SLIDER_PINS[i], INPUT);
  }
  Serial.begin(BAUD_RATE);
  // On the 32U4 boards the USB CDC needs a moment; we don't block forever
  // so the device still works headless if no PC is listening.
}

void loop() {
  handleSerialCommands();

  unsigned long now = millis();
  if (now - lastSend >= SEND_INTERVAL) {
    lastSend = now;
    updateSliderValues();
    sendSliderValues();
  }
}

void handleSerialCommands() {
  // Read a full newline-terminated command if one is waiting.
  static char buf[24];
  static byte idx = 0;

  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (idx > 0) {
        buf[idx] = '\0';
        processCommand(buf);
        idx = 0;
      }
    } else if (idx < (sizeof(buf) - 1)) {
      buf[idx++] = c;
    }
  }
}

void processCommand(const char* cmd) {
  if (strcmp(cmd, "barj-id?") == 0) {
    Serial.print("BARJ|");
    Serial.print(FW_VERSION);
    Serial.print("|");
    Serial.println(NUM_SLIDERS);
  } else if (strcmp(cmd, "barj-ping") == 0) {
    Serial.println("BARJ|pong");
  }
}

void updateSliderValues() {
  for (int i = 0; i < NUM_SLIDERS; i++) {
    analogSliderValues[i] = analogRead(SLIDER_PINS[i]);
  }
}

void sendSliderValues() {
  String out = "";
  for (int i = 0; i < NUM_SLIDERS; i++) {
    out += String(analogSliderValues[i]);
    if (i < NUM_SLIDERS - 1) out += "|";
  }
  Serial.println(out);
}
