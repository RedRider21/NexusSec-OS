# ~/.bashrc - NexusSec. bash legge questo file nelle shell interattive
# non-login (i terminali aperti dal desktop). Condividiamo il prompt con ash
# sorgiando lo stesso rcfile (shrc), cosi' lo stile e' unico e commutabile.
[ -r "$HOME/.config/nxs/shrc" ] && . "$HOME/.config/nxs/shrc"
