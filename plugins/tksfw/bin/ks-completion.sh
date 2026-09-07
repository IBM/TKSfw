# ks — shell completion (bash ≥ 3.2 and zsh via bashcompinit). Source from ~/.zshrc / ~/.bashrc:
#   source "<framework home>/tools/ks-completion.sh"        (checkout)
#   source "<plugin root>/bin/ks-completion.sh"             (plugin)
_ks_complete() {
  local cur prev words
  cur="${COMP_WORDS[COMP_CWORD]}"
  prev="${COMP_WORDS[COMP_CWORD-1]}"
  if [ "$COMP_CWORD" -eq 1 ]; then
    words="self operator project routing ledger harness doctor dev help version"
  else
    case "${COMP_WORDS[1]}" in
      self)     words="install version home" ;;
      operator) words="set show" ;;
      project)  words="init update enable disable status drift reset --full --json --archive --label --keep-agents --registry --dry-run --yes --force" ;;
      routing)  words="show check resolve use --clear" ;;
      ledger)   words="check find export archive-plan archive --refs --json --prefix --before --dry-run --out --archive --session --csv changes lessons events handoffs decisions deliverables tasks all" ;;
      harness)  words="sync retrust --check --ack" ;;
      dev)      words="build test release" ;;
      *)        words="" ;;
    esac
  fi
  COMPREPLY=( $(compgen -W "$words" -- "$cur") )
}
if [ -n "$ZSH_VERSION" ]; then
  autoload -U +X bashcompinit && bashcompinit
fi
complete -F _ks_complete ks
