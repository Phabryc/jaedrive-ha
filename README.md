# JaeDrive per Home Assistant

Porta in Home Assistant i dati della tua auto registrati da [JaeDrive](https://jaedrive.com):
contachilometri, tagliando, batteria, carburante, autonomie, ultimo parcheggio, ultimo viaggio e
statistiche degli ultimi 30 giorni. Gli aggiornamenti arrivano in push, senza aprire porte a casa.

**Sola lettura**: da Home Assistant non si comanda l'auto.

**Requisiti**
- Home Assistant 2026.11 o successivo.
- Un account JaeDrive con **abbonamento cloud attivo**: l'integrazione è gratuita, ma i dati
  dell'auto arrivano al cloud solo con l'abbonamento. Se scade, il collegamento resta e le entità
  vanno in "non disponibile"; al rinnovo tutto riparte da solo.

## Installazione

1. In Home Assistant: **Impostazioni → Marketplace → Aggiungi da link** e incolla l'indirizzo di
   questo repository (finché JaeDrive non è nel catalogo serve collegare GitHub).
2. Installa **JaeDrive**.
3. **Impostazioni → Dispositivi e servizi → Aggiungi integrazione → JaeDrive**.
4. Apri il link che compare, entra in JaeDrive e premi **Autorizza**. Puoi scegliere se condividere
   anche la posizione del parcheggio. La finestra di Home Assistant si completa da sola.

Per scollegare: sito JaeDrive → Impostazioni → Home Assistant → **Scollega**.

## Cosa crea

Un dispositivo per auto, più un dispositivo "JaeDrive" per l'abbonamento.

| Entità | Note |
|---|---|
| Contachilometri, km in elettrico / ibrido | statistiche a lungo termine |
| Km al tagliando, data tagliando | |
| Batteria, livello carburante, autonomie | se l'auto le espone |
| Parcheggio (`device_tracker`), parcheggiata da | solo con il permesso alla posizione |
| Ultimo viaggio: partenza, arrivo, fine, km, consumo, litri, velocità media, durata, quota elettrica | come le card del dettaglio viaggio sul sito |
| Ultimo viaggio, solo plug-in: km elettrici/ibridi, kWh, kWh/100 km, batteria inizio/fine, potenza e ricarica massime, energia recuperata | |
| Trip A e Trip B in corso: km, consumo, litri, dal (+ km elettrici e kWh sulle plug-in) | il contatore manuale non ancora azzerato; etichetta nell'attributo `label` |
| Km, consumo, quota elettrica ultimi 30 giorni | |
| Viaggio (`event`) | `trip_ended` a ogni viaggio concluso, per le automazioni |
| Abbonamento cloud, scadenza abbonamento | diagnostica |

Gli `entity_id` sono fissi e uguali in ogni lingua di Home Assistant:
`sensor.jaedrive_<chiave>` (es. `sensor.jaedrive_odometer`, `device_tracker.jaedrive_park`,
`event.jaedrive_trip`) e `binary_sensor.jaedrive_subscription_problem` /
`sensor.jaedrive_subscription_expires` per l'account. Con più auto la seconda prende `_2` in fondo
(`sensor.jaedrive_odometer_2`). I nomi mostrati invece sono tradotti.

Trip A/B: il cloud riconosce lo slot dall'etichetta predefinita "Trip A"/"Trip B"; se l'hai
rinominata nell'app, A è il contatore aperto da più tempo.

Contachilometri, batteria, data del tagliando e "dati aggiornati" ci sono sempre (vuoti finché
l'auto non manda il dato), carburante e autonomia su tutte tranne le elettriche. Le altre entità
di cui l'auto non ha il dato non vengono create.

## Plancia pronta

[`dashboards/jaedrive.yaml`](dashboards/jaedrive.yaml): una plancia con sole card standard
(tile, mappa, registro, grafici), niente da installare. Impostazioni > Plance > Aggiungi plancia >
"Nuova plancia da zero", poi matita > tre puntini > "Editor di configurazione grezza", incollare il
file: non c'è niente da cambiare. I nomi delle card vengono dalle entità e seguono la lingua di
Home Assistant; solo i titoli delle sezioni sono fissi, in inglese. Istruzioni e sezione in più per
plug-in ed elettriche sono nei commenti del file.

## Pubblicazione (note per chi mantiene il repo)

- Ogni versione è una **release GitHub** (non basta il tag) con `version` di `manifest.json`
  uguale al tag.
- I controlli `hacs/action` e `hassfest` girano in `.github/workflows/validate.yml`.
- Il codice nasce nel monorepo JaeDrive in `integrations/home-assistant/`; il design è in
  `cloud/HOME_ASSISTANT_INTEGRATION.md`.
