/*
 * web_page.h — the CyberLamp control page, served at http://cyberlamp.local
 *
 * Single self-contained page: no external fonts, scripts or CDNs, so it
 * works on a LAN with no internet access.
 *
 * Accessibility (WCAG 2.1 AA):
 *   - Text contrast ≥ 4.5:1, badges and controls ≥ 3:1 against their background.
 *   - Mode buttons are real <button>s with aria-pressed, so they work with
 *     Tab/Enter/Space and announce their on/off state to screen readers.
 *   - The active mode is shown by an "Active" pill and a border, not by color alone.
 *   - Sliders are native range inputs with visible labels and live values.
 *   - Visible :focus-visible outline on every control.
 *   - Status messages use an aria-live region.
 */

#pragma once

const char controlPageHtml[] PROGMEM = R"rawliteral(<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CyberLamp</title>
<style>
	:root {
		--page-background: #f3f4f6;
		--card-background: #ffffff;
		--text-primary: #111827;     /* 17.7:1 on white */
		--text-secondary: #4b5563;   /* 7.6:1 on white */
		--divider-color: #d1d5db;
		--focus-color: #1d4ed8;      /* 6.7:1 on white */
		--active-color: #1d4ed8;
		--amber-color: #b45309;      /* 5.0:1 on white */
		--teal-color: #0f766e;       /* 5.5:1 on white */
	}
	* { box-sizing: border-box; }
	body {
		margin: 0;
		padding: 16px;
		background: var(--page-background);
		color: var(--text-primary);
		font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
		font-size: 16px;
		line-height: 1.4;
	}
	main { max-width: 480px; margin: 0 auto; }
	.card {
		background: var(--card-background);
		border-radius: 12px;
		margin-bottom: 16px;
		overflow: hidden;
	}
	.card-row {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 14px 16px;
	}
	.card-row + .card-row { border-top: 0.5px solid var(--divider-color); }
	.badge {
		flex: 0 0 22px;
		width: 22px;
		height: 22px;
		border-radius: 50%;
	}
	.row-text { flex: 1; min-width: 0; }
	.row-title { font-weight: 600; margin: 0; font-size: 16px; }
	.row-subtitle { color: var(--text-secondary); font-size: 14px; margin: 2px 0 0; }
	.section-label {
		font-size: 11px;
		font-variant: small-caps;
		text-transform: lowercase;
		letter-spacing: 0.06em;
		font-weight: 600;
		color: var(--text-secondary);
		margin: 20px 4px 8px;
	}
	h1 { font-size: 20px; margin: 0; }

	/* Mode buttons look like card rows but are real buttons. */
	.mode-button {
		width: 100%;
		border: 2px solid transparent;
		background: var(--card-background);
		color: inherit;
		font: inherit;
		text-align: left;
		cursor: pointer;
		border-radius: 0;
	}
	.mode-button[aria-pressed="true"] { border-color: var(--active-color); border-radius: 12px; }
	.mode-button:hover { background: #f9fafb; }
	.pill {
		display: none;
		padding: 2px 10px;
		border-radius: 999px;
		font-size: 12px;
		font-weight: 600;
		background: var(--active-color);
		color: #ffffff;              /* 6.7:1 on the blue pill */
	}
	.mode-button[aria-pressed="true"] .pill { display: inline-block; }

	/* Sliders */
	.slider-row { display: block; padding: 14px 16px; }
	.slider-row + .slider-row { border-top: 0.5px solid var(--divider-color); }
	.slider-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
	.slider-header label { font-weight: 600; }
	.slider-header output { color: var(--text-secondary); font-variant-numeric: tabular-nums; }
	input[type="range"] { width: 100%; height: 32px; margin: 0; }
	#amber-level { accent-color: var(--amber-color); }
	#white-level { accent-color: var(--teal-color); }

	/* Visible keyboard focus on every control. */
	button:focus-visible,
	input:focus-visible {
		outline: 3px solid var(--focus-color);
		outline-offset: 2px;
	}

	.status { color: var(--text-secondary); font-size: 14px; text-align: center; min-height: 20px; }
</style>
</head>
<body>
<main>
	<div class="card">
		<div class="card-row">
			<span class="badge" style="background: var(--amber-color)" aria-hidden="true"></span>
			<div class="row-text">
				<h1>CyberLamp</h1>
				<p class="row-subtitle">Salvaged EQB DRL module · cyberlamp.local</p>
			</div>
		</div>
	</div>

	<h2 class="section-label" id="mode-heading">Mode</h2>
	<div class="card" id="mode-list" role="group" aria-labelledby="mode-heading"></div>

	<h2 class="section-label">Brightness</h2>
	<div class="card">
		<div class="slider-row">
			<div class="slider-header">
				<label for="amber-level">Amber string</label>
				<output id="amber-level-value" for="amber-level">–</output>
			</div>
			<input type="range" id="amber-level" min="0" max="100" step="1" value="80">
		</div>
		<div class="slider-row">
			<div class="slider-header">
				<label for="white-level">White string</label>
				<output id="white-level-value" for="white-level">–</output>
			</div>
			<input type="range" id="white-level" min="0" max="100" step="1" value="50">
		</div>
	</div>

	<p class="status" id="status-message" role="status" aria-live="polite"></p>
</main>

<script>
	const modeListElement = document.getElementById('mode-list');
	const amberSlider = document.getElementById('amber-level');
	const whiteSlider = document.getElementById('white-level');
	const amberValueOutput = document.getElementById('amber-level-value');
	const whiteValueOutput = document.getElementById('white-level-value');
	const statusMessageElement = document.getElementById('status-message');

	let modeButtonsHaveBeenBuilt = false;
	let sliderSendTimer = null;

	// Shows a short message in the live region (screen readers announce it).
	function showStatus(messageText) {
		statusMessageElement.textContent = messageText;
	}

	// Builds one button per mode the first time state arrives.
	// Text is set with textContent, never innerHTML, so nothing is injected as markup.
	function buildModeButtons(modeList) {
		modeListElement.textContent = '';
		for (const modeInfo of modeList) {
			const modeButton = document.createElement('button');
			modeButton.type = 'button';
			modeButton.className = 'mode-button card-row';
			modeButton.dataset.modeId = modeInfo.id;
			modeButton.setAttribute('aria-pressed', 'false');

			const badge = document.createElement('span');
			badge.className = 'badge';
			badge.style.background = modeInfo.color;
			badge.setAttribute('aria-hidden', 'true');

			const textBlock = document.createElement('span');
			textBlock.className = 'row-text';
			const title = document.createElement('span');
			title.className = 'row-title';
			title.style.display = 'block';
			title.textContent = modeInfo.name;
			const subtitle = document.createElement('span');
			subtitle.className = 'row-subtitle';
			subtitle.style.display = 'block';
			subtitle.textContent = modeInfo.description;
			textBlock.append(title, subtitle);

			const activePill = document.createElement('span');
			activePill.className = 'pill';
			activePill.textContent = 'Active';
			activePill.setAttribute('aria-hidden', 'true');  // aria-pressed already conveys this

			modeButton.append(badge, textBlock, activePill);
			modeButton.addEventListener('click', () => sendUpdate({ mode: modeInfo.id }));
			modeListElement.append(modeButton);
		}
		modeButtonsHaveBeenBuilt = true;
	}

	// Reflects the lamp's state in the page.
	function renderState(lampState) {
		if (!modeButtonsHaveBeenBuilt) {
			buildModeButtons(lampState.modes);
		}
		for (const modeButton of modeListElement.querySelectorAll('.mode-button')) {
			const isActiveMode = modeButton.dataset.modeId === lampState.mode;
			modeButton.setAttribute('aria-pressed', isActiveMode ? 'true' : 'false');
		}
		// Don't yank a slider out from under someone who is dragging it.
		if (document.activeElement !== amberSlider) {
			amberSlider.value = lampState.amberLevel;
		}
		if (document.activeElement !== whiteSlider) {
			whiteSlider.value = lampState.whiteLevel;
		}
		amberValueOutput.textContent = amberSlider.value + '%';
		whiteValueOutput.textContent = whiteSlider.value + '%';
	}

	async function fetchState() {
		try {
			const response = await fetch('/api/state');
			renderState(await response.json());
			showStatus('');
		} catch (error) {
			showStatus('Can’t reach the lamp. Check that it’s powered and on Wi-Fi.');
		}
	}

	// Sends changes as a form-encoded POST; the lamp replies with its new state.
	async function sendUpdate(changes) {
		try {
			const response = await fetch('/api/state', {
				method: 'POST',
				body: new URLSearchParams(changes)
			});
			if (!response.ok) {
				throw new Error('HTTP ' + response.status);
			}
			renderState(await response.json());
			showStatus('');
		} catch (error) {
			showStatus('Update failed. Try again.');
		}
	}

	// Sliders: update the readout immediately, send to the lamp after a short pause
	// so dragging doesn't flood it with requests.
	function handleSliderInput() {
		amberValueOutput.textContent = amberSlider.value + '%';
		whiteValueOutput.textContent = whiteSlider.value + '%';
		clearTimeout(sliderSendTimer);
		sliderSendTimer = setTimeout(() => {
			sendUpdate({ amberLevel: amberSlider.value, whiteLevel: whiteSlider.value });
		}, 150);
	}
	amberSlider.addEventListener('input', handleSliderInput);
	whiteSlider.addEventListener('input', handleSliderInput);

	fetchState();
	// Refresh every few seconds so the page stays in sync if the button is pressed.
	setInterval(fetchState, 4000);
</script>
</body>
</html>
)rawliteral";
