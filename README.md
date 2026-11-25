<p align="center">
  <img src="https://raw.githubusercontent.com/Phabryc/jaedrive-ha/main/custom_components/jaedrive/brand/logo.png" alt="JaeDrive" height="96">
</p>

# JaeDrive for Home Assistant

Brings the data of your car recorded by [JaeDrive](https://jaedrive.com) into Home Assistant:
odometer, service, battery, fuel, ranges, last parking spot, last trip, Trip A/B and statistics of
the last 30 days. Updates are pushed by the cloud: no ports to open at home.

**Read only**: the car cannot be controlled from Home Assistant.

**Requirements**
- Home Assistant 2026.11 or later.
- A JaeDrive account with an **active cloud subscription**: the integration is free, but the car
  data reaches the cloud only with the subscription. If it expires the link stays and the entities
  become "unavailable"; everything restarts by itself when it is renewed.

## Installation

1. In Home Assistant: **Settings → Marketplace → Add from link** and paste the address of this
   repository (until JaeDrive is in the catalog, GitHub has to be linked).
2. Install **JaeDrive** and restart Home Assistant.
3. **Settings → Devices & services → Add integration → JaeDrive**.
4. Open the link that appears, sign in to JaeDrive and press **Authorize**. You can choose whether
   to share the parking location too. The Home Assistant window completes by itself.

To unlink: JaeDrive website → Settings → Home Assistant → **Unlink**.

## Dashboard

**Settings → Dashboards → Add dashboard → JaeDrive** (under "Custom"). That's all: the dashboard
builds itself from the JaeDrive entities, one view per car, and updates together with the
integration. It only shows what your car has: the electric data on plug-in hybrids and EVs, the map
only if you shared the location.

To change it, open the dashboard, pencil → three dots → **Take control**: it becomes a normal
dashboard you can edit, but from then on it no longer updates by itself.

## Cards

The cards are in the card picker of every dashboard (search "JaeDrive"), nothing to install:

| Card | Shows |
|---|---|
| `custom:jaedrive-car-card` | battery, fuel and ranges, odometer, service, last update, subscription warning |
| `custom:jaedrive-last-trip-card` | route, distance, duration, average speed, consumption, fuel, electric share; on plug-ins also kWh, battery, peak power and regeneration |
| `custom:jaedrive-trips-card` | Trip A and Trip B side by side |
| `custom:jaedrive-stats-card` | distance, trips, consumption and electric share of the last 30 days |
| `custom:jaedrive-parking-card` | address, parked since and map (with the location permission) |

Every card takes an optional `device_id` to pick the car; without it, the first car is used:

```yaml
type: custom:jaedrive-last-trip-card
device_id: 0123456789abcdef  # optional
```

Texts follow the language of Home Assistant (English and Italian; other languages fall back to
English). Tap a value to open its history.

A dashboard made only of built-in cards, to copy and change by hand, is in
[`dashboards/jaedrive.yaml`](dashboards/jaedrive.yaml).

## Entities

One device per car, plus a "JaeDrive" device for the subscription.

| Entity | Notes |
|---|---|
| Odometer, electric / hybrid distance | long-term statistics |
| Distance to service, service date | |
| Battery, fuel level, ranges | if the car exposes them |
| Parking (`device_tracker`), parked since | only with the location permission |
| Last trip: start, destination, end time, distance, consumption, fuel, average speed, duration, electric share | as the trip detail cards on the website |
| Last trip, plug-in only: electric/hybrid km, kWh, kWh/100 km, battery at start/end, peak power and regeneration, recovered energy | |
| Running Trip A and Trip B: distance, consumption, fuel, since (+ electric km and kWh on plug-ins) | the manual counter not reset yet; its label is in the `label` attribute |
| Distance, consumption, electric share of the last 30 days | |
| Trip (`event`) | `trip_ended` at the end of every trip, for automations |
| Cloud subscription, subscription expiry | diagnostic |

Entity ids are fixed and the same in every Home Assistant language: `sensor.jaedrive_<key>`
(e.g. `sensor.jaedrive_odometer`, `device_tracker.jaedrive_park`, `event.jaedrive_trip`) and
`binary_sensor.jaedrive_subscription_problem` / `sensor.jaedrive_subscription_expires` for the
account. With more cars the second one gets `_2` at the end (`sensor.jaedrive_odometer_2`). Names
are translated.

Trip A/B: the cloud recognizes the slot from the default label "Trip A"/"Trip B"; if you renamed it
in the app, A is the counter that has been running for longer.

Units follow your JaeDrive profile, the same as the car app and the website: change them in the app
(Settings) or on the website (Settings → App preferences) and Home Assistant follows. Consumption is
shown in km/L, L/100 km, mpg or gal/100 mi (imperial gallon, as in the app); distances and speeds in
km or miles. A unit you pick by hand in the entity settings stays until the profile changes.

Odometer, battery, service date and "data updated" are always there (empty until the car sends
them), fuel and range on every car except EVs. Other entities the car has no data for are not
created.

## Publishing (notes for maintainers)

- Every version is a **GitHub release** (a tag is not enough) with the `version` of
  `manifest.json` equal to the tag.
- The `hacs/action` and `hassfest` checks run in `.github/workflows/validate.yml`.
- The code lives in the JaeDrive monorepo under `integrations/home-assistant/`.
