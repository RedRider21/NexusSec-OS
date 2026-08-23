# Build di NexusSec OS (base Alpine Linux)

NexusSec e' una live x86_64 basata su **Alpine** (musl, apk, OpenRC) con
desktop **Openbox** e la barra/pannello in **Python** (riusati da TinyCore).
La specializzazione e' a **profili** (Pen Testing, Forensics, OSINT, Web):
ogni profilo e' un **meta-pacchetto apk** `sec-profile-*`; i tool pesanti
(Metasploit, ZAP, ...) girano in **container Podman**; i sandboxing leggero
e' con **bubblewrap**.

> La build dell'ISO va eseguita **su Alpine** (serve `abuild` + `mkimage.sh`
> + privilegi). Non e' eseguibile su una distro generica senza questi
> strumenti. Gli sfondi (`make wallpaper`) si generano ovunque (ImageMagick).

## Componenti

```
NexusSec-OS/
├── overlay/                 # payload iniettato nella live (apkovl)
│   ├── usr/local/bin|lib    # nxs_cc (pannello+CC), nxs_profiles, nxs_wizards
│   │                        #   (procedure guidate), nxs_browser, binari nxs-*
│   ├── usr/local/share/nexussec/  # profiles.json + repo.json + wizards.json
│   ├── home/nexus/          # .xinitrc, .config/openbox, .themes, sfondi
│   └── etc/local.d/         # init runtime (OpenRC 'local')
├── aports/                  # APKBUILD: nexussec-base + sec-profile-*
├── build-alpine/            # genapkovl + profilo mkimage + questo README
└── build/make-wallpaper.sh  # sfondi per profilo
```

## Prerequisiti (su Alpine)

```sh
doas apk add alpine-sdk build-base abuild git xorriso squashfs-tools \
             mkinitfs grub grub-efi dosfstools
abuild-keygen -a -i        # chiave per firmare i pacchetti
```

## 1) Compilare i meta-pacchetti

```sh
cd aports/nexussec-base   && abuild -r
for p in pentest forensics osint web; do
  cd ../sec-profile-$p && abuild -r
done
# Gli .apk firmati finiscono in ~/packages/<repo>/x86_64/
```

> NOTA pacchetti: i `depends` dei `sec-profile-*` usano i nomi Alpine dei tool.
> Alcuni sono in `community`/`testing`: abilita i repo in `/etc/apk/repositories`.
> I tool non in apk (vedi `overlay/usr/local/share/nexussec/repo.json`, metodo
> `container`/`pip`) NON sono nei meta-pacchetti: li ottiene `nxs-tool` a runtime.

## 2) Generare gli sfondi

```sh
make wallpaper      # -> overlay/home/nexus/.themes/NexusSec-Core/backgrounds/
```

## 3) Costruire l'ISO con mkimage

```sh
git clone https://gitlab.alpinelinux.org/alpine/aports.git
cp build-alpine/mkimg.nexussec.sh      aports/scripts/
cp build-alpine/genapkovl-nexussec.sh  aports/scripts/

sh aports/scripts/mkimage.sh \
   --profile nexussec \
   --outdir "$PWD/out" \
   --arch x86_64 \
   --repository http://dl-cdn.alpinelinux.org/alpine/edge/main \
   --repository http://dl-cdn.alpinelinux.org/alpine/edge/community \
   --repository "$HOME/packages/nexussec"     # i nostri meta-pacchetti
```

Risultato: `out/nexussec-*.iso` (~0.5 GB, boot BIOS+EFI; il pavimento reale con
kernel lts + desktop GTK + Podman + firmware wireless e' ~500-540 MB). Provala in
QEMU (servono >=2-3 GB di RAM: la live installa il desktop in tmpfs al boot):

```sh
qemu-system-x86_64 -m 4096 -enable-kvm -cdrom out/nexussec-*.iso -boot d
```

## Flusso a runtime (la "magia")

1. Boot Alpine (~150 MB) -> autologin `nexus` -> `startx` -> Openbox.
2. L'autostart lancia pannello + sfondo + **selettore profilo** (`nxs-profile`).
3. Scegli "Pen Testing": `nxs-tool` esegue `apk add --no-cache sec-profile-pentest`
   (oppure `apk del` del profilo precedente con la spunta "monomissione").
4. Il menu del pannello mostra solo i tool del profilo; cliccandone uno,
   `nxs-tool launch` lo installa-se-serve (apk / Podman / pip) e lo esegue.
5. Le **procedure guidate** (`nxs-wizard`) orchestrano catene di tool con
   Modalita' (intensita'), Opzioni a spunta, interruttore **Stealth** (via Tor,
   con `tor`/`torsocks` in `nexussec-base`) e passaggio dati tra step; un
   costruttore grafico crea wizard personalizzati in `~/.config/nxs/wizards/`.
