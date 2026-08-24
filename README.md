# chargeBIG for Home Assistant

[![Validate](https://github.com/KevinCluse/homeassistant-chargebig/actions/workflows/validate.yml/badge.svg)](https://github.com/KevinCluse/homeassistant-chargebig/actions/workflows/validate.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)

Control and monitor a [chargeBIG](https://chargebig.com/) (carica) EV charge point from
Home Assistant: start, pause and resume charging, and see live power, energy and
session cost — so you can automate charging from other events, e.g. "start charging when
the car's charge cable is plugged in".

This talks directly to the same backend the [carica web app](https://app.carica.chargebig.de/)
uses. There is no official chargeBIG API; the protocol was reconstructed from a capture
of the web app's own network traffic — see [`docs/api.md`](docs/api.md) for the details
and its limits. As an unofficial integration against an undocumented backend, it can
break if chargeBIG changes their app.

## Installation

### HACS (recommended)

1. HACS → the three-dot menu (top right) → **Custom repositories**.
2. Repository: `https://github.com/KevinCluse/homeassistant-chargebig`, category
   **Integration** → **Add**.
3. Find "chargeBIG" in HACS and install it.
4. Restart Home Assistant.

### Manual

Copy `custom_components/chargebig` into your Home Assistant `config/custom_components/`
directory and restart Home Assistant.

## Setup

**Settings → Devices & Services → Add Integration → chargeBIG.**

1. Enter the email and password of your carica/chargeBIG account.
2. Enter the charge point code (the five-character ID from the QR code / NFC tag on the
   charge point, e.g. `XXYXX`).

Add the integration again for each additional charge point on your account — every
charge point becomes its own Home Assistant device.

## Entities

Per charge point:

| Entity | Description |
|---|---|
| `switch.<name>_charging` | On while a session is charging. Turning it on starts a new session (or resumes a paused one); turning it off pauses. |
| `sensor.<name>_session_energy` | Energy delivered in the current session (kWh). Usable as an Energy Dashboard consumer. |
| `sensor.<name>_power` | Current charging power (W). |
| `sensor.<name>_status` | Raw session status (`charging`, `paused_evse`, …). |
| `sensor.<name>_session_duration` | Duration of the current session (disabled by default). |
| `sensor.<name>_session_start` | Timestamp the current session started. |
| `sensor.<name>_session_cost` | Cost of the current session, in your account's currency. |
| `sensor.<name>_charge_point_status` | Status as shown in the app (`Charging`, `Available`, …). |
| `sensor.<name>_power_limit` | Power currently allotted to this charge point (load management). |
| `sensor.<name>_price_per_kwh` | Price of the active/preferred tariff. |
| `binary_sensor.<name>_online` | Whether the charge point reports itself online. |
| `binary_sensor.<name>_charging` | On while energy is actually flowing. |

## Services

- `chargebig.start_charging` (`device_id`, optional `tariff_id`)
- `chargebig.pause_charging` (`device_id`)
- `chargebig.resume_charging` (`device_id`)
- `chargebig.refresh` (`device_id`)

## Example: start charging when the car is plugged in

```yaml
automation:
  - alias: Start chargeBIG when the car is plugged in
    triggers:
      - trigger: state
        entity_id: binary_sensor.skoda_charging_cable_connected
        to: "on"
        for: "00:00:30"
    conditions:
      - condition: state
        entity_id: binary_sensor.chargebig_xxyxx_online
        state: "on"
    actions:
      - action: switch.turn_on
        target:
          entity_id: switch.chargebig_xxyxx_charging
```

`switch.turn_on` starts a fresh session if none is running, and resumes one that's
paused — so this one automation covers both cases.

## Limitations

- **Ending a session isn't exposed.** The backend calls seen so far only cover
  pause/resume; ending a session appears to require unplugging the cable at the charge
  point. If you find an explicit "end session" action in the app, please open an issue
  with a HAR capture of it (redact your password/tokens first) so it can be added.
- **No history endpoint.** The backend doesn't expose a list of past sessions in what
  was captured, so history relies on Home Assistant's own long-term statistics via the
  energy sensor rather than an imported session list.
- This is a reverse-engineered, unofficial integration. It is not affiliated with or
  endorsed by MAHLE chargeBIG GmbH.

## Diagnostics

**Settings → Devices & Services → chargeBIG → ⋮ → Download diagnostics** produces a
redacted dump (no email, password or tokens) useful for bug reports.

## License

MIT, see [LICENSE](LICENSE).
