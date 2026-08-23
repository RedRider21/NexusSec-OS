SHELL := /bin/bash
ROOT  := $(shell pwd)
BUILD := $(ROOT)/build
OUT   := $(ROOT)/out
OVERLAY := $(ROOT)/overlay
PYLIB := $(OVERLAY)/usr/local/lib
SHARE := $(OVERLAY)/usr/local/share/nexussec

.PHONY: all help wallpaper browser-icon icons apkovl check iso clean

all: help

help:
	@echo "NexusSec OS (base Alpine) - target Makefile"
	@echo
	@echo "  make wallpaper     genera gli sfondi per profilo (ImageMagick)"
	@echo "  make browser-icon  genera l'icona PNG di NexusSec Browser"
	@echo "  make icons         genera i temi icone per profilo (PIL, accent)"
	@echo "  make check         sintassi Python + validazione JSON (host)"
	@echo "  make apkovl        crea out/nexussec.apkovl.tar.gz dall'overlay"
	@echo "  make iso           costruisce l'ISO (richiede Alpine + mkimage)"
	@echo "  make clean         rimuove out/"
	@echo
	@echo "Build completa dell'ISO: vedi build-alpine/README.md (serve Alpine)."

wallpaper:
	@$(BUILD)/make-wallpaper.sh

browser-icon:
	@$(BUILD)/make-browser-icon.sh

icons:
	@python3 $(BUILD)/make-icons.py

# Controlli eseguibili su qualsiasi host (CI): compila i moduli Python e
# valida i JSON di profili/repo.
check:
	@python3 -m py_compile $(PYLIB)/nxs_cc/*.py $(PYLIB)/nxs_profiles/*.py && echo "py OK"
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
