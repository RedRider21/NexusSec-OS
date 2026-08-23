"""Sistema di profili operativi NexusSec.

Sottocomponenti:
  model      - caricamento profiles.json/repo.json, profilo corrente, sfondo.
  isolation  - download e esecuzione isolata dei tool via bubblewrap.
  selector   - selettore grafico (GTK3) del profilo all'avvio.

Il selettore imposta il profilo, cambia lo sfondo inerente alla modalita'
e fa si' che il menu del pannello mostri solo i tool pertinenti.
"""
