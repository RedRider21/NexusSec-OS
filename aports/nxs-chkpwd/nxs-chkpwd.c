/* nxs-chkpwd - verifica una password contro /etc/shadow (helper setuid root).
 *
 * Uso:  echo -n "<password>" | nxs-chkpwd <utente>
 * La password si legge da STDIN (mai da argv). Ritorna:
 *   0 = password corretta
 *   1 = password errata / account senza password
 *   2 = errore (utente assente, niente privilegi, input mancante)
 *
 * Pensato per il greeter di NexusSec: Alpine non usa PAM di default, quindi si
 * verifica direttamente l'hash shadow con crypt(3). Essendo setuid root puo'
 * leggere /etc/shadow anche quando il chiamante non e' root e senza doas.
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <string.h>
#include <shadow.h>
#include <crypt.h>

int main(int argc, char **argv)
{
    if (argc < 2)
        return 2;

    char pw[512];
    if (!fgets(pw, sizeof pw, stdin))
        return 2;
    pw[strcspn(pw, "\n")] = '\0';          /* togli il newline finale */

    struct spwd *sp = getspnam(argv[1]);    /* richiede root -> setuid */
    if (!sp || !sp->sp_pwdp) {
        memset(pw, 0, sizeof pw);
        return 2;
    }

    const char *hash = sp->sp_pwdp;
    if (hash[0] == '\0' || hash[0] == '!' || hash[0] == '*') {
        memset(pw, 0, sizeof pw);
        return 1;                           /* account bloccato / senza password */
    }

    char *c = crypt(pw, hash);
    int ok = (c != NULL && strcmp(c, hash) == 0);
    memset(pw, 0, sizeof pw);               /* non lasciare la password in RAM */
    return ok ? 0 : 1;
}
