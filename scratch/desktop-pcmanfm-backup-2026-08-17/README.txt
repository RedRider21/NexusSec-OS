BACKUP configurazione DESKTOP basata su pcmanfm (stato 2026-08-17, PRIMA di
valutare il file manager Python di Vesper come sostituto di pcmanfm --desktop).

Per TORNARE INDIETRO a pcmanfm:
  cp autostart.orig  ../../overlay/home/nexus/.config/openbox/autostart
  cp libfm.conf.orig ../../overlay/home/nexus/.config/libfm/libfm.conf
  (poi ricostruire l'ISO)

Riga chiave in autostart che gestisce il desktop:
  pcmanfm --desktop --profile=NexusSec &
  pcmanfm --set-wallpaper <png> --wallpaper-mode=stretch   (via nxs-tool apply)

Limiti pcmanfm che motivano il rimpiazzo (richiesta utente):
  - le icone non trascinate si auto-riallineano (griglia), niente "freeze layout";
  - icona spostata invisibile finche' non si clicca (bug ridisegno libfm);
  - nessuna opzione "disattiva auto-arrange" come nei DE convenzionali.
