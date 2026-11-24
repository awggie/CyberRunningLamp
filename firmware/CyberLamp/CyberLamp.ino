/*
 * CyberLamp — cyberpunk ambient lamp built from a salvaged Mercedes EQB
 * Hella DRL / turn-signal LED module.
 *
 * Board: Seeed Studio XIAO ESP32S3 (Arduino-ESP32 core 3.x)
 *
 * What it does:
 *   - Drives the module's two LED strings independently with PWM:
 *       amber string (module pin 2) and white string (module pin 4),
 *       both returning through module pin 1 (shared negative).
 *   - Each string is fed by its own LM317 constant-current source (~27 mA),
 *     switched on its high side by a PNP transistor. PWM on that switch
 *     sets brightness. GPIO HIGH = LEDs on.
 *   - Modes: off, steady amber, steady white, amber breathing,
 *     "failing streetlight" glitch, and glitch + white arc flashes.
 *   - Control three ways:
 *       1. Web page on your home Wi-Fi at http://cyberlamp.local
 *       2. A push button (cycles modes)
 *       3. Serial monitor: send 0–5 to pick a mode
 *   - Runs fine without Wi-Fi: if the network is down or secrets.h still
 *     has placeholders, the lamp just works offline.
 *
 * Setup: copy secrets.example.h to secrets.h and fill in your Wi-Fi.
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include <math.h>

#include "secrets.h"
#include "web_page.h"

// ============================================================
// Hardware pin assignments (XIAO ESP32S3 pin labels)
// ============================================================

// Each output drives a 2N3904 base (through 4.7 kΩ), which in turn pulls
// the base of the 2N5401 PNP high-side switch low to turn a string on.
const int amberChannelPin = D0;   // amber turn-signal string (module pin 2)
const int whiteChannelPin = D1;   // white DRL string (module pin 4)

// Momentary push button to GND. Uses the internal pull-up, so pressed = LOW.
// D3 is used (not D2) because D2 is GPIO3, an ESP32-S3 strapping pin.
const int modeButtonPin = D3;

// ============================================================
// PWM settings
// ============================================================

// 1 kHz is fast enough to be flicker-free to the eye and slow enough that the
// PNP switch and LM317 settle cleanly on every pulse.
const uint32_t pwmFrequencyHz = 1000;

// 12-bit resolution gives 4096 brightness steps, which keeps slow fades smooth.
const uint8_t pwmResolutionBits = 12;
const uint32_t maxDutyValue = (1u << pwmResolutionBits) - 1;

// Eyes perceive brightness non-linearly. Raising the requested brightness to
// this power before converting to duty makes slider and fade steps look even.
const float gammaExponent = 2.2f;

// ============================================================
// Network settings
// ============================================================

const char *deviceHostname = "cyberlamp";              // → http://cyberlamp.local
const unsigned long wifiReconnectCheckIntervalMs = 30000;  // how often to retry if Wi-Fi drops

WebServer controlWebServer(80);
bool isMdnsRunning = false;
unsigned long lastWifiCheckTimeMs = 0;

// ============================================================
// Lamp modes
// ============================================================

enum LampMode {
	MODE_OFF = 0,
	MODE_AMBER_STEADY,
	MODE_WHITE_STEADY,
	MODE_AMBER_BREATHE,
	MODE_FAILING_STREETLIGHT,
	MODE_STREETLIGHT_ARCING,
	MODE_COUNT  // not a real mode: the number of modes, used for loops and cycling
};

// Short machine-friendly IDs used by the web API (index matches LampMode).
const char *lampModeIds[MODE_COUNT] = {
	"off", "amber", "white", "breathe", "glitch", "arcing"
};

// Human-readable names and one-line descriptions shown on the web page.
const char *lampModeNames[MODE_COUNT] = {
	"Off", "Amber", "White", "Breathe", "Failing streetlight", "Streetlight + arcing"
};
const char *lampModeDescriptions[MODE_COUNT] = {
	"Both strings dark",
	"Steady amber glow",
	"Steady white glow",
	"Slow amber pulse",
	"Amber with random stutters",
	"Stutters plus white arc flashes"
};

// Badge colors for the web page (all at least 3:1 contrast on white).
const char *lampModeBadgeColors[MODE_COUNT] = {
	"#6b7280",  // off: gray
	"#b45309",  // amber
	"#0f766e",  // white: teal, so the badge stays visible on a white card
	"#b45309",  // breathe: amber
	"#b91c1c",  // glitch: red
	"#7e22ce"   // arcing: purple
};

LampMode currentLampMode = MODE_AMBER_STEADY;

// User-adjustable maximum brightness for each string, 0.0–1.0.
// Effects scale within this ceiling. Full scale ≈ 27 mA, set by the LM317 resistor.
float amberChannelLevel = 0.8f;
float whiteChannelLevel = 0.5f;

// ============================================================
// Breathing effect
// ============================================================

const unsigned long breathingPeriodMs = 6000;     // one full in-and-out breath
const float breathingFloorFraction = 0.08f;       // never fully dark, like a pilot light
unsigned long breathingStartTimeMs = 0;

// ============================================================
// Glitch effect
// ============================================================

// Describes how a glitching channel behaves. The same engine produces both
// the amber "failing streetlight" stutter and the white "arc flash" pops.
struct GlitchProfile {
	float restingBrightness;          // level held during quiet periods (0–1)
	float glitchBrightnessMin;        // range of the "wrong" level during a stutter
	float glitchBrightnessMax;
	int minStuttersPerBurst;          // how many wrong/right flickers per burst
	int maxStuttersPerBurst;
	unsigned long minStepDurationMs;  // how long each flicker step lasts
	unsigned long maxStepDurationMs;
	unsigned long minQuietPeriodMs;   // calm time between bursts
	unsigned long maxQuietPeriodMs;
};

// Live state for one glitching channel.
struct GlitchState {
	bool isInBurst;
	int remainingBurstSteps;          // counts down; even steps glitch, odd steps restore
	unsigned long nextStepTimeMs;
	float currentBrightness;
};

// Amber: holds near full, then drops out in short irregular stutters.
const GlitchProfile failingStreetlightProfile = {
	1.0f,           // resting at full (scaled by amberChannelLevel)
	0.0f, 0.25f,    // dropouts go nearly dark
	2, 6,           // 2–6 stutters per burst
	15, 90,         // each step 15–90 ms
	3000, 12000     // 3–12 s of calm between bursts
};

// White: normally dark, with rare, brief, bright pops like electrical arcing.
const GlitchProfile arcFlashProfile = {
	0.0f,           // resting dark
	0.35f, 1.0f,    // flashes are bright
	1, 3,           // 1–3 pops per burst
	10, 40,         // very short
	6000, 20000     // 6–20 s between bursts
};

GlitchState amberGlitchState;
GlitchState whiteGlitchState;

// ============================================================
// Button debounce state
// ============================================================

const unsigned long buttonDebounceMs = 40;
int lastStableButtonReading = HIGH;
int lastRawButtonReading = HIGH;
unsigned long lastButtonChangeTimeMs = 0;

// ============================================================
// Helpers
// ============================================================

// Returns a random float between minValue and maxValue (inclusive).
float randomFloatBetween(float minValue, float maxValue) {
	return minValue + (maxValue - minValue) * (random(0, 10001) / 10000.0f);
}

// Converts a perceived brightness (0–1) into a PWM duty value with gamma correction.
uint32_t brightnessToDuty(float perceivedBrightness) {
	perceivedBrightness = constrain(perceivedBrightness, 0.0f, 1.0f);
	float gammaCorrectedBrightness = powf(perceivedBrightness, gammaExponent);
	return (uint32_t)(gammaCorrectedBrightness * maxDutyValue + 0.5f);
}

// Puts a glitch channel into its quiet state and schedules its first burst.
void resetGlitchState(GlitchState &glitchState, const GlitchProfile &profile, unsigned long nowMs) {
	glitchState.isInBurst = false;
	glitchState.remainingBurstSteps = 0;
	glitchState.currentBrightness = profile.restingBrightness;
	glitchState.nextStepTimeMs = nowMs + random(profile.minQuietPeriodMs, profile.maxQuietPeriodMs + 1);
}

// Advances a glitch channel's state machine and returns its current brightness (0–1).
// Non-blocking: call it every loop; it only changes state when a step is due.
float updateGlitchBrightness(GlitchState &glitchState, const GlitchProfile &profile, unsigned long nowMs) {
	// Nothing to do until the next scheduled step.
	// (Signed difference keeps this correct when millis() wraps after ~49 days.)
	if ((long)(nowMs - glitchState.nextStepTimeMs) < 0) {
		return glitchState.currentBrightness;
	}

	// Quiet period over: start a new burst. Each stutter is two steps
	// (one "wrong" level, one back to resting), so the burst always ends restored.
	if (!glitchState.isInBurst) {
		glitchState.isInBurst = true;
		int stutterCount = random(profile.minStuttersPerBurst, profile.maxStuttersPerBurst + 1);
		glitchState.remainingBurstSteps = stutterCount * 2;
	}

	if (glitchState.remainingBurstSteps > 0) {
		bool isGlitchStep = (glitchState.remainingBurstSteps % 2 == 0);
		glitchState.currentBrightness = isGlitchStep
			? randomFloatBetween(profile.glitchBrightnessMin, profile.glitchBrightnessMax)
			: profile.restingBrightness;
		glitchState.remainingBurstSteps--;
		glitchState.nextStepTimeMs = nowMs + random(profile.minStepDurationMs, profile.maxStepDurationMs + 1);
	} else {
		// Burst finished: settle back to resting and schedule the next burst.
		resetGlitchState(glitchState, profile, nowMs);
	}

	return glitchState.currentBrightness;
}

// Smooth breathing curve from the floor up to 1.0 and back, using a cosine.
float calculateBreathingBrightness(unsigned long nowMs) {
	unsigned long positionInCycleMs = (nowMs - breathingStartTimeMs) % breathingPeriodMs;
	float cycleFraction = (float)positionInCycleMs / (float)breathingPeriodMs;
	float wave = 0.5f - 0.5f * cosf(2.0f * PI * cycleFraction);  // 0 → 1 → 0
	return breathingFloorFraction + (1.0f - breathingFloorFraction) * wave;
}

// Switches modes and resets any effect timers so each mode starts cleanly.
void setLampMode(LampMode newMode) {
	unsigned long nowMs = millis();
	currentLampMode = newMode;
	breathingStartTimeMs = nowMs;
	resetGlitchState(amberGlitchState, failingStreetlightProfile, nowMs);
	resetGlitchState(whiteGlitchState, arcFlashProfile, nowMs);
	Serial.printf("Mode: %s\n", lampModeNames[currentLampMode]);
}

// Looks up a mode by its API ID. Returns true and sets foundMode if it exists.
bool findLampModeById(const String &modeId, LampMode &foundMode) {
	for (int modeIndex = 0; modeIndex < MODE_COUNT; modeIndex++) {
		if (modeId == lampModeIds[modeIndex]) {
			foundMode = (LampMode)modeIndex;
			return true;
		}
	}
	return false;
}

// ============================================================
// Output: compute each channel's brightness for the current mode
// ============================================================

void updateLampOutputs() {
	unsigned long nowMs = millis();

	// Effect brightness for each string, 0–1, before applying the user's level.
	float amberEffectBrightness = 0.0f;
	float whiteEffectBrightness = 0.0f;

	switch (currentLampMode) {
		case MODE_OFF:
			break;
		case MODE_AMBER_STEADY:
			amberEffectBrightness = 1.0f;
			break;
		case MODE_WHITE_STEADY:
			whiteEffectBrightness = 1.0f;
			break;
		case MODE_AMBER_BREATHE:
			amberEffectBrightness = calculateBreathingBrightness(nowMs);
			break;
		case MODE_FAILING_STREETLIGHT:
			amberEffectBrightness = updateGlitchBrightness(amberGlitchState, failingStreetlightProfile, nowMs);
			break;
		case MODE_STREETLIGHT_ARCING:
			amberEffectBrightness = updateGlitchBrightness(amberGlitchState, failingStreetlightProfile, nowMs);
			whiteEffectBrightness = updateGlitchBrightness(whiteGlitchState, arcFlashProfile, nowMs);
			break;
		default:
			break;
	}

	// Scale by each string's user-set ceiling, then write gamma-corrected PWM.
	ledcWrite(amberChannelPin, brightnessToDuty(amberEffectBrightness * amberChannelLevel));
	ledcWrite(whiteChannelPin, brightnessToDuty(whiteEffectBrightness * whiteChannelLevel));
}

// ============================================================
// Inputs: button and serial
// ============================================================

// Debounced button: each press cycles to the next mode.
void handleModeButton() {
	int rawButtonReading = digitalRead(modeButtonPin);
	unsigned long nowMs = millis();

	if (rawButtonReading != lastRawButtonReading) {
		lastButtonChangeTimeMs = nowMs;
		lastRawButtonReading = rawButtonReading;
	}

	bool readingHasSettled = (nowMs - lastButtonChangeTimeMs) > buttonDebounceMs;
	if (readingHasSettled && rawButtonReading != lastStableButtonReading) {
		lastStableButtonReading = rawButtonReading;
		bool buttonWasJustPressed = (rawButtonReading == LOW);
		if (buttonWasJustPressed) {
			setLampMode((LampMode)((currentLampMode + 1) % MODE_COUNT));
		}
	}
}

// Serial monitor control: send a digit 0–5 to jump to that mode.
void handleSerialCommands() {
	while (Serial.available() > 0) {
		char receivedCharacter = (char)Serial.read();
		if (receivedCharacter >= '0' && receivedCharacter < '0' + MODE_COUNT) {
			setLampMode((LampMode)(receivedCharacter - '0'));
		}
	}
}

// ============================================================
// Wi-Fi and web server
// ============================================================

// True when secrets.h still has the template placeholders.
bool wifiCredentialsAreMissing() {
	return strcmp(homeWifiNetworkName, "YOUR_WIFI_NAME") == 0 || strlen(homeWifiNetworkName) == 0;
}

// Builds the JSON the web page uses to render itself.
String buildStateJson() {
	String stateJson = "{";
	stateJson += "\"mode\":\"" + String(lampModeIds[currentLampMode]) + "\",";
	stateJson += "\"amberLevel\":" + String((int)roundf(amberChannelLevel * 100)) + ",";
	stateJson += "\"whiteLevel\":" + String((int)roundf(whiteChannelLevel * 100)) + ",";
	stateJson += "\"modes\":[";
	for (int modeIndex = 0; modeIndex < MODE_COUNT; modeIndex++) {
		if (modeIndex > 0) {
			stateJson += ",";
		}
		stateJson += "{\"id\":\"" + String(lampModeIds[modeIndex]) + "\",";
		stateJson += "\"name\":\"" + String(lampModeNames[modeIndex]) + "\",";
		stateJson += "\"description\":\"" + String(lampModeDescriptions[modeIndex]) + "\",";
		stateJson += "\"color\":\"" + String(lampModeBadgeColors[modeIndex]) + "\"}";
	}
	stateJson += "]}";
	return stateJson;
}

// GET / → the control page.
void handleControlPageRequest() {
	controlWebServer.send_P(200, "text/html", controlPageHtml);
}

// GET /api/state → current mode and levels as JSON.
void handleGetStateRequest() {
	controlWebServer.send(200, "application/json", buildStateJson());
}

// POST /api/state with any of: mode=<id>, amberLevel=0–100, whiteLevel=0–100.
// Unknown modes are rejected; levels are clamped to 0–100.
void handleSetStateRequest() {
	if (controlWebServer.hasArg("mode")) {
		LampMode requestedMode;
		if (!findLampModeById(controlWebServer.arg("mode"), requestedMode)) {
			controlWebServer.send(400, "application/json", "{\"error\":\"unknown mode\"}");
			return;
		}
		if (requestedMode != currentLampMode) {
			setLampMode(requestedMode);
		}
	}
	if (controlWebServer.hasArg("amberLevel")) {
		int requestedAmberPercent = constrain(controlWebServer.arg("amberLevel").toInt(), 0, 100);
		amberChannelLevel = requestedAmberPercent / 100.0f;
	}
	if (controlWebServer.hasArg("whiteLevel")) {
		int requestedWhitePercent = constrain(controlWebServer.arg("whiteLevel").toInt(), 0, 100);
		whiteChannelLevel = requestedWhitePercent / 100.0f;
	}
	controlWebServer.send(200, "application/json", buildStateJson());
}

void setupWifiAndWebServer() {
	if (wifiCredentialsAreMissing()) {
		Serial.println("Wi-Fi: no credentials in secrets.h — running offline.");
		return;
	}

	// Station mode only (no access point), auto-reconnect on drops.
	WiFi.mode(WIFI_STA);
	WiFi.setHostname(deviceHostname);
	WiFi.setAutoReconnect(true);
	WiFi.begin(homeWifiNetworkName, homeWifiPassword);
	Serial.printf("Wi-Fi: connecting to %s ...\n", homeWifiNetworkName);

	controlWebServer.on("/", HTTP_GET, handleControlPageRequest);
	controlWebServer.on("/api/state", HTTP_GET, handleGetStateRequest);
	controlWebServer.on("/api/state", HTTP_POST, handleSetStateRequest);
	controlWebServer.onNotFound([]() {
		controlWebServer.send(404, "text/plain", "Not found");
	});
	controlWebServer.begin();
}

// Non-blocking Wi-Fi housekeeping: start mDNS once connected and nudge
// a reconnect if the network has been down for a while.
void maintainWifiConnection() {
	if (wifiCredentialsAreMissing()) {
		return;
	}

	bool isWifiConnected = (WiFi.status() == WL_CONNECTED);

	if (isWifiConnected && !isMdnsRunning) {
		if (MDNS.begin(deviceHostname)) {
			MDNS.addService("http", "tcp", 80);
			isMdnsRunning = true;
		}
		Serial.printf("Wi-Fi: connected. Open http://%s.local or http://%s\n",
			deviceHostname, WiFi.localIP().toString().c_str());
	}

	if (!isWifiConnected) {
		if (isMdnsRunning) {
			MDNS.end();
			isMdnsRunning = false;
		}
		unsigned long nowMs = millis();
		if (nowMs - lastWifiCheckTimeMs > wifiReconnectCheckIntervalMs) {
			lastWifiCheckTimeMs = nowMs;
			WiFi.reconnect();
		}
	}
}

// ============================================================
// Arduino entry points
// ============================================================

void setup() {
	Serial.begin(115200);

	// Seed randomness from the ESP32's hardware random number generator,
	// so glitch timing differs on every boot.
	randomSeed(esp_random());

	// Attach PWM to both channel pins (core 3.x API) and start dark.
	ledcAttach(amberChannelPin, pwmFrequencyHz, pwmResolutionBits);
	ledcAttach(whiteChannelPin, pwmFrequencyHz, pwmResolutionBits);
	ledcWrite(amberChannelPin, 0);
	ledcWrite(whiteChannelPin, 0);

	pinMode(modeButtonPin, INPUT_PULLUP);

	setLampMode(MODE_AMBER_STEADY);
	setupWifiAndWebServer();
}

void loop() {
	handleModeButton();
	handleSerialCommands();
	maintainWifiConnection();
	if (!wifiCredentialsAreMissing()) {
		controlWebServer.handleClient();
	}
	updateLampOutputs();
}
