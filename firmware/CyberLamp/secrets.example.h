/*
 * secrets.example.h — template for your Wi-Fi credentials.
 *
 * Setup:
 *   1. Copy this file to "secrets.h" in the same folder.
 *   2. Fill in your home network name and password in secrets.h.
 *
 * secrets.h is listed in .gitignore so your password never gets committed.
 * If you leave the placeholder values in place, the lamp skips Wi-Fi and
 * runs offline (button + serial control still work).
 */

#pragma once

// Your home Wi-Fi network name (SSID). Must be 2.4 GHz: the ESP32-S3 has no 5 GHz radio.
const char *homeWifiNetworkName = "YOUR_WIFI_NAME";

// Your home Wi-Fi password.
const char *homeWifiPassword = "YOUR_WIFI_PASSWORD";
