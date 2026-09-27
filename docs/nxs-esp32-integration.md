# TODO — `nxs-esp32`: flash + import del gadget ESP32 nella distro

> **Puntatore.** La **specifica completa** (autorevole, tenuta aggiornata) sta nel
> progetto del gadget:
>
> - `../nexussec-esp32/docs/nxs-esp32-integration.md`
> - GitHub: <https://github.com/RedRider21/nexussec-esp32/blob/master/docs/nxs-esp32-integration.md>
>
> Non duplicare qui il contenuto: leggere da lì per non divergere.

## In sintesi (cosa implementare in QUESTA distro)
Creare il tool **`nxs-esp32`** che:
1. **Flash** della scheda **ESP32-DIV V2** via `esptool` (chip `esp32s3`), con
   **selezione profilo/immagine** e opzione **ripristino firmware originale**
   (`../nexussec-esp32/firmware/vendor/ESP32-DIV-v2-v1.7.2.bin`, MIT). Immagine
   nostra "merged" da scrivere a **0x0**.
2. **Import** dei dati del gadget:
   - Wardriving `/WARDRIVE.csv` (`BSSID,SSID,Enc,Channel,RSSI,Lat,Lon,Timestamp`)
     → **HORUS** (`overlay/usr/local/lib/nxs_horus/`), scartando lat/lon `0.0`.
   - Handshake/PMKID `*.hc22000` → `~/NexusSec-loot/`.

## Dove
- `overlay/usr/local/bin/nxs-esp32` (+ `overlay/usr/local/lib/nxs_esp32/`),
  voce nel pannello/Centro di Controllo (riusa `nxs_cc.common`), dip. APK `esptool`.

Dettagli, pin, CLI e GUI: vedi la specifica linkata sopra.
