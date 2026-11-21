# The rn-forge home

```text
$RNF_HOME/                  default ~/.rn-forge
  env.sh                    owned by the home; written by every installer
  bin/<command>             links, one per command a product puts on PATH
  completions/_<command>    links, one zsh completion script per command
  <product>/                the product's own; its layout is its business
```

- **Location.** `$RNF_HOME`, or `~/.rn-forge` when that is unset or empty.

- **Ownership.** A product writes only inside `<product>/` and the links it
  declares under `bin/` and `completions/`. It never removes `env.sh`, `bin/`
  or `completions/`, and it removes only links that still point where it put
  them.

- **Links** point through the product's `current`, so an upgrade or rollback
  never touches them.

- **`completions/`** holds zsh completion functions named `_<command>`, the
  `fpath` convention. Nothing else goes there.

- **`env.sh`** has exactly this text, with `<home>` replaced by the home's
  absolute path:

    ```sh
    # rn-forge home environment, schema 1. Written by rn-forge installers; do not edit.
    # Source it from your shell's rc file, before compinit: source "<home>/env.sh"
    export RNF_HOME="<home>"
    case ":${PATH}:" in
      *":${RNF_HOME}/bin:"*) ;;
      *) export PATH="${RNF_HOME}/bin:${PATH}" ;;
    esac
    if [ -n "${ZSH_VERSION:-}" ]; then
      fpath=("${RNF_HOME}/completions" "${fpath[@]}")
    fi
    ```

- **Writing `env.sh`.** Every install writes `env.sh` when it is missing, or
  when its first line names a lower schema than the writer's. A file with the
  same schema or a higher one is left alone, so an older installer never
  downgrades it. A file whose first line is not a schema line is the user's:
  it is left alone, and the installer warns.

- **The hint.** When `$RNF_HOME/bin` is not on `PATH`, an install ends by
  printing `source "<home>/env.sh"` and the advice to add that line to the rc
  file before `compinit`. No installer edits an rc file. macsetup, which owns
  its users' `~/.zshrc`, sources `env.sh` from its profile.

- **Schema changes.** A change to `env.sh` raises the schema number, changes
  this page, and ships in every writer.
