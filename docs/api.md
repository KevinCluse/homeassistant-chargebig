# chargeBIG / carica API (reverse-engineered)

This is not a documented, supported API. Everything below was reconstructed from a HAR
capture of the official web app (`https://app.carica.chargebig.com/`) taken by the
integration's author against their own account, and may change or break at any time
without notice.

## Base URL

```
https://carica.chargebig.com
```

The web app itself is served from `https://app.carica.chargebig.com/` (a Flutter web
build); `app.carica.chargebig.de` redirects there. All API calls go to the bare
`carica.chargebig.com` host, not the `app.` subdomain.

## Authentication

`POST /v1/auth/charger-user/login`

```json
{ "email": "you@example.com", "password": "…", "fireBaseId": "", "language": "de" }
```

→ `200`

```json
{ "accessToken": "<JWT, HS512>", "refreshToken": "<JWT, HS512>" }
```

The access token observed in the capture carried a 40-hour expiry (`iat`/`exp` claims),
the refresh token 30 days. No `/refresh` endpoint appeared in the capture, so the
integration re-authenticates with the stored email/password once the access token is
rejected, rather than exchanging the refresh token.

Every authenticated request sends:

```
Authorization: Bearer <accessToken>
```

This exact header was not visible in the capture (it was taken in the browser's
"sanitized" HAR export, which strips `Authorization`), but it is strongly implied:
the CORS preflights for authenticated endpoints request
`Access-Control-Request-Headers: authorization,content-type` and the backend answers
`Access-Control-Allow-Headers: authorization, content-type` and additionally exposes
`Access-Control-Expose-Headers: accessToken, refreshToken` — i.e. the backend both
accepts an `Authorization` header and may hand out rotated tokens through response
headers of that same name. Given the login endpoint returns JWTs, `Bearer` is the only
sensible scheme. Confirmed indirectly (a 401 without it, 200 with it) the first time the
integration runs against a real account.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/auth/charger-user/login` | Login, see above |
| GET | `/v1/charger-user/get-account` | Profile of the logged-in user |
| GET | `/v1/charge-point/info/{code}?language=DE&includeRFIDs=false` | Charge point + tariffs |
| GET | `/v1/payment-methods` | Stored payment tokens |
| POST | `/v1/charge-point/{code}/charge` | **Start** a charging session |
| GET | `/v1/charging-processes/active` | All sessions currently running on the account |
| GET | `/v1/charging-processes/{id}` | One session, full payload (includes the client's ToS text) |
| GET | `/v1/charging-processes/light/{id}` | Same session, without the ToS text — used for polling |
| POST | `/v1/charging-processes/{id}/pause` | **Pause** a running session |
| POST | `/v1/charging-processes/{id}/resume` | **Resume** a paused session |
| GET | `/v1/charging-processes/{id}/history` | Watt samples plotted for the running session |
| GET | `/v1/app/updateRequired/{appVersion}` | App-store version gate, irrelevant here |

### Charge point info

`GET /v1/charge-point/info/XXYXX?language=DE&includeRFIDs=false`

```json
{
  "code": "XXYXX",
  "hardwareId": "70b3d586920d4",
  "chargingProcessId": 294806,
  "plugType": "TYPE2",
  "maxChargingPowerWatt": 7400,
  "chargePointStatus": "Charging",
  "cabinetStatus": "CHARGEMODE",
  "isOnline": true,
  "location": { "id": 38, "name": "…", "currency": "EURO" },
  "tariffs": [
    {
      "id": 214,
      "name": "chargeBIG - 7,4 kW-Laden",
      "centsPerKwh": 40,
      "baseFeeCents": 0,
      "priority": 10,
      "paymentMethods": ["VISA", "MASTER_CARD", "SEPA", "PAYPAL", "VOUCHER"]
    }
  ],
  "paymentMethods": ["VISA", "MASTER_CARD", "PAYPAL", "VOUCHER", "SEPA"]
}
```

`chargingProcessId` is `0`/absent when nothing is running at that charge point.

### Start a session

`POST /v1/charge-point/XXYXX/charge`

```json
{
  "paymentMethod": "SEPA",
  "paymentToken": "<from /v1/payment-methods>",
  "voucherCode": null,
  "sessionId": null,
  "tariffId": 214,
  "isGuest": false,
  "chargePointCode": "XXYXX",
  "language": "de"
}
```

If a session is already running, the backend answers `406`:

```json
{
  "timestamp": "2026-08-24T21:40:19.598540438",
  "status": 406,
  "error": "Not Acceptable",
  "message": "ChargePoint Unavailable",
  "messageDe": "Ladepunkt nicht verfügbar"
}
```

Every error response observed follows this shape. `messageDe` is used directly for the
error the integration surfaces in Home Assistant.

### Session status (light)

`GET /v1/charging-processes/light/294806`

```json
{
  "chargingProcessDto": {
    "id": 294806,
    "startDate": "2026-08-24T17:52:31.938545",
    "endDate": null,
    "duration": "PT3H48M3.656488181S",
    "amountCent": 0,
    "chargedAmountCorrectedKWh": 16.559,
    "chargingActivePowerKW": 4.443,
    "chargingStatus": "PAUSED_EVSE",
    "errorCode": 0
  },
  "chargePointCode": "XXYXX",
  "powerLimitKW": 4.68,
  "energyLimitWh": 0,
  "deratingIndex": 0
}
```

Observed `chargingStatus` values: `CHARGING`, `PAUSED_EVSE`. No other values were seen in
the capture. The integration treats anything starting with `PAUSED`/`SUSPENDED` as
"session exists but is halted" and everything else as unknown, rather than assuming this
list is exhaustive.

`duration` is a `java.time.Duration.toString()` value (ISO-8601, e.g.
`PT3H47M23.455350362S`).

### Timestamps

Timestamps such as `startDate` carry no offset. They are UTC: in the `406` error payload
above, the server-generated `timestamp` field matched the HTTP `Date` response header of
the very same response (`Mon, 24 Aug 2026 21:40:19 GMT`) to the second — and an HTTP
`Date` header is always GMT/UTC by definition.

### Not covered by the capture

- **Ending a session outright.** Only pause/resume were exercised; the account owner
  ends sessions by unplugging the cable. If the app exposes an explicit "end charging"
  action, it needs its own capture to add.
- **A list of past charging sessions.** `…/history` only returns the power curve of the
  *currently running* session, not a session list. The integration instead relies on
  Home Assistant's own long-term statistics (`state_class: total_increasing` on the
  energy sensor) for that.
