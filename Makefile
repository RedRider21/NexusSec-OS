SHELL := /bin/bash
ROOT  := $(shell pwd)
BUILD := $(ROOT)/build
OUT   := $(ROOT)/out
OVERLAY := $(ROOT)/overlay
PYLIB := $(OVERLAY)/usr/local/lib
SHARE := $(OVERLAY)/usr/local/share/nexussec

.PHONY: all help wallpaper panel-wallpapers browser-icon icons themes panel-themes logo-emblem apkovl check iso clean

all: help

help:
	@echo "NexusSec OS (base Alpine) - target Makefile"
	@echo
	@echo "  make wallpaper     genera gli sfondi per profilo (ImageMagick)"
	@echo "  make panel-wallpapers  genera gli sfondi abbinati alle skin pannello"
	@echo "  make browser-icon  genera l'icona PNG di NexusSec Browser"
	@echo "  make icons         genera i temi icone per profilo (PIL, accent)"
	@echo "  make themes        genera i temi Openbox coordinati (Retro/Cards per profilo)"
	@echo "  make panel-themes  genera le skin colore del pannello (barra + menu)"
	@echo "  make logo-emblem   genera il logo ASCII dell'emblema per nxs-fetch"
	@echo "  make check         sintassi Python + validazione JSON (host)"
	@echo "  make apkovl        crea out/nexussec.apkovl.tar.gz dall'overlay"
	@echo "  make iso           costruisce l'ISO (richiede Alpine + mkimage)"
	@echo "  make clean         rimuove out/"
	@echo
	@echo "Build completa dell'ISO: vedi build-alpine/README.md (serve Alpine)."

wallpaper:
	@$(BUILD)/make-wallpaper.sh

panel-wallpapers:
	@python3 $(BUILD)/make-panel-wallpapers.py

browser-icon:
	@$(BUILD)/make-browser-icon.sh

icons:
	@python3 $(BUILD)/make-icons.py

themes:
	@python3 $(BUILD)/make-openbox-themes.py

panel-themes:
	@python3 $(BUILD)/make-panel-themes.py

logo-emblem:
	@python3 $(BUILD)/make-logo-emblem.py

# Controlli eseguibili su qualsiasi host (CI): compila i moduli Python e
# valida i JSON di profili/repo.
check:
	@python3 -m py_compile $(PYLIB)/nxs_*/*.py && echo "py OK (tutti i pacchetti nxs_*)"
	@find $(PYLIB) -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null; true
	@command -v node >/dev/null 2>&1 && for f in $(PYLIB)/nxs_horus/web/*.js; do node --check $$f || exit 1; done && echo "JS HORUS OK" || true
	@python3 -c "import json,glob; [json.load(open(f)) for f in glob.glob('$(SHARE)/*.json')]; print('JSON OK')"

apkovl:
	@mkdir -p $(OUT)
	@$(ROOT)/build-alpine/genapkovl-nexussec.sh nexussec

iso:
	@if command -v abuild >/dev/null 2>&1; then \
	  echo "Per la build ISO segui build-alpine/README.md (mkimage.sh)."; \
	else \
	  echo "ERRORE: build ISO richiede Alpine + abuild + mkimage.sh."; \
	  echo "Vedi build-alpine/README.md."; exit 1; \
	fi

clean:
	rm -rf "$(OUT)"
