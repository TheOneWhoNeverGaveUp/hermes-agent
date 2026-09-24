savedcmd_towngu_kmod.mod := printf '%s\n'   towngu_kmod.o | awk '!x[$$0]++ { print("./"$$0) }' > towngu_kmod.mod
