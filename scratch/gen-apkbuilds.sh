#!/bin/sh
# Genera gli APKBUILD dei tool C non presenti in Alpine (repo nexussec).
# I sha512sums vengono calcolati dall'harness (abuild checksum).
#
# Note musl/gcc-15 (DURAMENTE imparate, non re-derivare):
#  - gcc >=14 promuove a ERRORE: implicit-function-declaration, int-conversion,
#    incompatible-pointer-types, implicit-int. Si declassano con -Wno-error=...
#  - gcc >=10 usa -fno-common di default -> "multiple definition" di globali in
#    header senza extern. Fix: -fcommon.
#  - musl: niente glibc *64 (fopen64...) -> -Dfopen64=fopen ecc.; strcasestr e
#    altre estensioni richiedono -D_GNU_SOURCE; alcuni sorgenti omettono include
#    (fcntl.h/limits.h/cstdint) -> force-include con -include.
#  - I Makefile scritti a mano IGNORANO $CFLAGS dell'ambiente: passare le flag
#    sulla riga di make (override) o, per gli autotools, via CFLAGS prima di
#    ./configure (che le sostituisce nel Makefile generato).
set -eu
AP="$(cd "$(dirname "$0")/.." && pwd)/aports"

mk() { mkdir -p "$AP/$1"; cat > "$AP/$1/APKBUILD"; }

# ---------------------------------------------------------------- dmitry (C)
mk dmitry <<'EOF'
# Maintainer: NexusSec <deplano.d@gmail.com>
pkgname=dmitry
pkgver=1.4.0
pkgrel=0
pkgdesc="Deepmagic Information Gathering Tool (whois/porte/sottodomini)"
url="https://github.com/jaygreig86/dmitry"
arch="x86_64"
license="GPL-3.0-or-later"
makedepends="autoconf automake"
# Pin al commit immutabile (tag/branch possono spostarsi o sparire -> 404).
_commit=f2b8961dabbd55486a5649a9803446b860ad28e7  # tag v1.4.0
source="$pkgname-$pkgver.tar.gz::https://github.com/jaygreig86/dmitry/archive/$_commit.tar.gz"
builddir="$srcdir/$pkgname-$_commit"
build() {
	cd "$builddir"
	[ -x ./configure ] || { autoreconf -fi || aclocal && autoconf; }
	./configure --prefix=/usr
	make
}
package() {
	cd "$builddir"
	install -Dm755 dmitry "$pkgdir"/usr/bin/dmitry
	# Niente man page (abuild rifiuta quelle non compresse; superflue su live).
}
EOF

# ---------------------------------------------------------------- foremost (C)
mk foremost <<'EOF'
# Maintainer: NexusSec <deplano.d@gmail.com>
pkgname=foremost
pkgver=1.5.7
pkgrel=0
pkgdesc="File carving forense per signature (recupero file cancellati)"
url="http://foremost.sourceforge.net/"
arch="x86_64"
license="custom"
# Pin al commit immutabile del branch master.
_commit=9b2ccf2a6d924e7a57971af6b92e6a287d28efb1
source="$pkgname-$pkgver.tar.gz::https://github.com/korczis/foremost/archive/$_commit.tar.gz"
builddir="$srcdir/foremost-$_commit"
build() {
	cd "$builddir"
	# Su musl non esiste fopen64: lo mappiamo a fopen (off_t e gia 64-bit).
	# Le define stanno in RAW_FLAGS (che porta anche -DVERSION): le appendo
	# per non perdere VERSION (override di CC romperebbe il -DVERSION).
	sed -i 's|^RAW_FLAGS = .*|& -D_FILE_OFFSET_BITS=64 -Dfopen64=fopen -Dlseek64=lseek -Dstat64=stat -Dfseeko64=fseeko -Dftello64=ftello -Doff64_t=off_t -fcommon|' Makefile
	make linux
}
package() {
	cd "$builddir"
	install -Dm755 foremost "$pkgdir"/usr/bin/foremost
	install -Dm644 foremost.conf "$pkgdir"/etc/foremost.conf
	# Niente man page: abuild rifiuta man pages non compresse (e gzip qui e
	# superfluo per una live). Il tool resta pienamente funzionante.
}
EOF

# ---------------------------------------------------------------- dirb (C)
mk dirb <<'EOF'
# Maintainer: NexusSec <deplano.d@gmail.com>
pkgname=dirb
pkgver=2.22
pkgrel=0
pkgdesc="Web content scanner (brute-force directory/file con wordlist)"
url="https://dirb.sourceforge.net/"
arch="x86_64"
license="GPL-2.0-or-later"
makedepends="curl-dev"
source="$pkgname-$pkgver.tar.gz::https://downloads.sourceforge.net/project/dirb/dirb/$pkgver/dirb222.tar.gz"
builddir="$srcdir/dirb222"
build() {
	cd "$builddir"
	chmod +x configure
	# -fcommon: i globali sono definiti negli header senza extern (multiple
	# definition con gcc >=10). configure sostituisce CFLAGS nel Makefile.
	CFLAGS="$CFLAGS -fcommon -D_GNU_SOURCE" ./configure --prefix=/usr
	make
}
package() {
	cd "$builddir"
	install -Dm755 dirb "$pkgdir"/usr/bin/dirb
	mkdir -p "$pkgdir"/usr/share/dirb
	cp -r wordlists "$pkgdir"/usr/share/dirb/ 2>/dev/null || true
}
EOF

# ---------------------------------------------------------------- medusa (C)
mk medusa <<'EOF'
# Maintainer: NexusSec <deplano.d@gmail.com>
pkgname=medusa
pkgver=2.2
pkgrel=0
pkgdesc="Brute-forcer di login modulare e parallelo"
url="https://github.com/jmk-foofus/medusa"
arch="x86_64"
license="GPL-2.0-or-later"
makedepends="openssl-dev libssh2-dev ncurses-dev"
# Pin al commit immutabile (tag 2.2).
_commit=5a7b76ee9fb48e4983719f074335b003b7fd6ad5
source="$pkgname-$pkgver.tar.gz::https://github.com/jmk-foofus/medusa/archive/$_commit.tar.gz"
builddir="$srcdir/$pkgname-$_commit"
unpack() {
	# README e un SYMLINK a README.md: con podman rootless tar tenta il chmod
	# sul link e aborta (Operation not permitted). Lo escludo dallo scompattamento.
	mkdir -p "$srcdir"
	tar -C "$srcdir" --exclude="$pkgname-$_commit/README" \
		-xzf "$srcdir/$pkgname-$pkgver.tar.gz"
}
prepare() {
	cd "$builddir"
	# OpenSSL 3 ha RIMOSSO SSLv2/SSLv3_client_method: li rimappo a SSLv23
	# (auto-negoziazione del protocollo migliore). TLSv1/SSLv23 restano.
	sed -i -e 's/SSLv2_client_method/SSLv23_client_method/g' \
	       -e 's/SSLv3_client_method/SSLv23_client_method/g' src/medusa-net.c
}
build() {
	cd "$builddir"
	chmod +x configure
	# configure gia committato (no autoreconf, evita AM_CONFIG_HEADER deprecato).
	# strcasestr richiede _GNU_SOURCE; -fcommon per i globali senza extern.
	# strcasestr richiede _GNU_SOURCE; -fcommon per i globali senza extern;
	# il callback keyboard-interactive di libssh2 ha firma "incompatibile"
	# (errore con gcc >=14) -> declassato a warning. Il modulo VNC usa la struct
	# DH di OpenSSL (resa opaca in OpenSSL 3) -> lo disabilito: medusa resta
	# completo per ssh/ftp/http/smb/rdp/mysql/telnet/... (tutti gli altri moduli).
	CFLAGS="$CFLAGS -fcommon -D_GNU_SOURCE -Wno-error=incompatible-pointer-types \
		-Wno-error=deprecated-declarations -Wno-error=implicit-function-declaration" \
		./configure --prefix=/usr --enable-static=no --enable-module-vnc=no
	make
}
package() {
	cd "$builddir"
	make DESTDIR="$pkgdir" install
	# abuild rifiuta man pages non compresse: per una live le rimuovo.
	rm -rf "$pkgdir"/usr/share/man
}
EOF

# ---------------------------------------------------------------- chkrootkit (C+sh)
mk chkrootkit <<'EOF'
# Maintainer: NexusSec <deplano.d@gmail.com>
pkgname=chkrootkit
pkgver=0.58b
pkgrel=0
pkgdesc="Rilevazione locale di rootkit"
url="http://www.chkrootkit.org/"
arch="x86_64"
license="BSD-2-Clause"
makedepends="linux-headers"
# Mirror Magentron senza tag 0.58b (404) e sito ufficiale offline -> pin al
# commit immutabile del branch master.
_commit=c00b5a40f61cc969e56fa2fe3375741c4164c896
source="$pkgname-$pkgver.tar.gz::https://github.com/Magentron/chkrootkit/archive/$_commit.tar.gz"
builddir="$srcdir/$pkgname-$_commit"
build() {
	cd "$builddir"
	# I force-include vanno dentro CC, NON in CFLAGS: alcune regole del Makefile
	# (es. chkdirs) usano solo ${LDFLAGS} e ignorano ${CFLAGS}, quindi limits.h
	# (PATH_MAX) non arriverebbe. Mettendoli in CC raggiungono OGNI regola.
	# Lascio CFLAGS=-DHAVE_LASTLOG_H del Makefile (non lo sovrascrivo).
	make sense CC="gcc -fcommon -D_GNU_SOURCE \
		-include fcntl.h -include limits.h -include signal.h -include unistd.h \
		-Wno-error=implicit-function-declaration -Wno-error=int-conversion \
		-Wno-error=incompatible-pointer-types -Wno-error=implicit-int"
}
package() {
	cd "$builddir"
	for b in chkrootkit chklastlog chkwtmp ifpromisc chkproc chkdirs chkutmp; do
		[ -f "$b" ] && install -Dm755 "$b" "$pkgdir"/usr/lib/chkrootkit/"$b" || true
	done
	install -Dm755 chkrootkit "$pkgdir"/usr/bin/chkrootkit
}
EOF

# ---------------------------------------------------------------- rkhunter (sh/perl)
mk rkhunter <<'EOF'
# Maintainer: NexusSec <deplano.d@gmail.com>
pkgname=rkhunter
pkgver=1.4.6
pkgrel=0
pkgdesc="Rootkit Hunter - scansione integrita e rootkit"
url="https://rkhunter.sourceforge.net/"
arch="noarch"
license="GPL-2.0-or-later"
depends="bash"
source="$pkgname-$pkgver.tar.gz::https://downloads.sourceforge.net/project/rkhunter/rkhunter/$pkgver/rkhunter-$pkgver.tar.gz"
builddir="$srcdir/$pkgname-$pkgver"
package() {
	cd "$builddir"
	sh installer.sh --layout custom . --install
	install -Dm755 files/rkhunter "$pkgdir"/usr/bin/rkhunter
	install -Dm644 files/rkhunter.conf "$pkgdir"/etc/rkhunter.conf
	mkdir -p "$pkgdir"/var/lib/rkhunter/db "$pkgdir"/usr/share/rkhunter
	cp -r files/* "$pkgdir"/usr/share/rkhunter/ 2>/dev/null || true
}
EOF

# ---------------------------------------------------------------- scalpel (C, autotools)
mk scalpel <<'EOF'
# Maintainer: NexusSec <deplano.d@gmail.com>
pkgname=scalpel
pkgver=1.60
pkgrel=0
pkgdesc="File carving veloce (fork di foremost)"
url="https://github.com/sleuthkit/scalpel"
arch="x86_64"
license="GPL-2.0-or-later"
makedepends="autoconf automake tre-dev linux-headers"
# Pin al commit immutabile del branch master.
_commit=16872619d0b889ddb566259074be24999c52f3d5
source="$pkgname-$pkgver.tar.gz::https://github.com/machn1k/Scalpel-2.0/archive/$_commit.tar.gz"
builddir="$srcdir/Scalpel-2.0-$_commit"
build() {
	cd "$builddir"
	# Shim error.h: glibc-only, assente in musl (scalpel.h lo include).
	mkdir -p "$builddir"/compat
	cat > "$builddir"/compat/error.h <<'SHIM'
#ifndef _NXS_ERROR_H
#define _NXS_ERROR_H
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <errno.h>
#include <stdlib.h>
static inline void error(int status, int errnum, const char *fmt, ...) {
	va_list ap;
	fflush(stdout);
	fputs("scalpel: ", stderr);
	va_start(ap, fmt); vfprintf(stderr, fmt, ap); va_end(ap);
	if (errnum) fprintf(stderr, ": %s", strerror(errnum));
	fputc('\n', stderr);
	if (status) exit(status);
}
#endif
SHIM
	# Ha configure (autotools) ma nessun Makefile finche non lo si lancia.
	chmod +x configure
	CFLAGS="$CFLAGS -fcommon -D_GNU_SOURCE -D_FILE_OFFSET_BITS=64 -I$builddir/compat \
		-Wno-error=implicit-function-declaration -Wno-error=int-conversion \
		-Wno-error=incompatible-pointer-types" ./configure --prefix=/usr
	make
}
package() {
	cd "$builddir"
	install -Dm755 scalpel "$pkgdir"/usr/bin/scalpel 2>/dev/null || \
		install -Dm755 src/scalpel "$pkgdir"/usr/bin/scalpel
	install -Dm644 scalpel.conf "$pkgdir"/etc/scalpel/scalpel.conf 2>/dev/null || true
}
EOF

# ---------------------------------------------------------------- bulk-extractor (C++)
mk bulk-extractor <<'EOF'
# Maintainer: NexusSec <deplano.d@gmail.com>
pkgname=bulk-extractor
pkgver=2.0.0
pkgrel=0
pkgdesc="Estrazione di feature (email/URL/carte) da immagini disco"
url="https://github.com/simsong/bulk_extractor"
arch="x86_64"
license="MIT"
makedepends="autoconf automake libtool flex openssl-dev zlib-dev expat-dev re2-dev linux-headers"
source="$pkgname-$pkgver.tar.gz::https://github.com/simsong/bulk_extractor/releases/download/v$pkgver/bulk_extractor-$pkgver.tar.gz"
builddir="$srcdir/bulk_extractor-$pkgver"
build() {
	cd "$builddir"
	# Shim per gli header glibc assenti in musl. Verificato a monte: l'UNICO
	# blocco a livello di header e sys/cdefs.h (definisce __BEGIN_DECLS/__END_DECLS,
	# usati da pcap_fake.h/net_ethernet.h/pyxpress.h). Niente err.h/execinfo/strlcpy.
	mkdir -p "$builddir"/compat/sys
	cat > "$builddir"/compat/sys/cdefs.h <<'SHIM'
#ifndef _NXS_SYS_CDEFS_H
#define _NXS_SYS_CDEFS_H
#ifdef __cplusplus
# define __BEGIN_DECLS extern "C" {
# define __END_DECLS }
#else
# define __BEGIN_DECLS
# define __END_DECLS
#endif
#ifndef __THROW
# define __THROW
#endif
#ifndef __nonnull
# define __nonnull(x)
#endif
#ifndef __wur
# define __wur
#endif
#endif
SHIM
	[ -x ./configure ] || ./bootstrap.sh
	# musl: uint16_t -> force-include <cstdint>; u_int (tipo BSD) -> _GNU_SOURCE
	# + sys/types.h force-included; cdefs -> shim sopra.
	CXXFLAGS="$CXXFLAGS -D_GNU_SOURCE -include cstdint -include sys/types.h -I$builddir/compat" \
	CFLAGS="$CFLAGS -fcommon -D_GNU_SOURCE -include sys/types.h -I$builddir/compat" \
		./configure --prefix=/usr
	make
}
package() {
	cd "$builddir"
	make DESTDIR="$pkgdir" install
	# abuild rifiuta man pages non compresse: per una live le rimuovo.
	rm -rf "$pkgdir"/usr/share/man
}
EOF

echo "APKBUILD generati in $AP per: dmitry foremost dirb medusa chkrootkit rkhunter scalpel bulk-extractor"
echo "(stegseek -> container docker.io/rickdejager/stegseek: mhash-dev assente in Alpine)"
