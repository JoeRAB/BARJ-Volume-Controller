// BARJ Volume Controller - Arduino Sketch
// Reads N potentiometers and sends values over serial in deej-compatible format:
// val0|val1|val2|...|valN\n  (values 0-1023)
//
// Wire each potentiometer:
//   Left pin  -> GND
//   Middle pin (wiper) -> A0, A1, A2, ...
//   Right pin -> 5V

const int NUM_SLIDERS = 5;           // Change to match your potentiometer count
const int ANALOG_PINS[NUM_SLIDERS] = {A0, A1, A2, A3, A4};
const int SEND_INTERVAL_MS = 10;     // Send every 10ms (~100Hz)

int values[NUM_SLIDERS] = {0};

void setup() {
  Serial.begin(9600);
  for (int i = 0; i < NUM_SLIDERS; i++) {
    pinMode(ANALOG_PINS[i], INPUT);
  }
}

void loop() {
  // Read all sliders
  for (int i = 0; i < NUM_SLIDERS; i++) {
    values[i] = analogRead(ANALOG_PINS[i]);
  }

  // Send as pipe-separated values
  for (int i = 0; i < NUM_SLIDERS; i++) {
    Serial.print(values[i]);
    if (i < NUM_SLIDERS - 1) {
      Serial.print("|");
    }
  }
  Serial.println();  // newline to terminate the message

  delay(SEND_INTERVAL_MS);
}
