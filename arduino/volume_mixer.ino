// BARJ Volume Controller — Arduino Sketch
// Uses the same format as deej: val0|val1|val2|...|valN\n
//
// Wire each potentiometer:
//   Left pin  (GND)   -> Arduino GND
//   Middle    (wiper) -> A0, A1, A2, A3, A4
//   Right pin (5V)    -> Arduino 5V

const int NUM_SLIDERS = 5;
const int analogInputs[NUM_SLIDERS] = {A0, A1, A2, A3, A4};

int analogSliderValues[NUM_SLIDERS];

void setup() {
  for (int i = 0; i < NUM_SLIDERS; i++) {
    pinMode(analogInputs[i], INPUT);
  }
  Serial.begin(9600);
}

void loop() {
  updateSliderValues();
  sendSliderValues();
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

// Uncomment to debug in Arduino Serial Monitor:
// void printSliderValues() {
//   for (int i = 0; i < NUM_SLIDERS; i++) {
//     String printedString = String("Slider #") + String(i + 1)
//                          + String(": ") + String(analogSliderValues[i]) + String(" mV");
//     Serial.write(printedString.c_str());
//     if (i < NUM_SLIDERS - 1) {
//       Serial.write(" | ");
//     } else {
//       Serial.write("\n");
//     }
//   }
// }
