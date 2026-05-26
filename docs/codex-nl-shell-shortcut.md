# Codex NL-to-Shell Shortcut

The `ctrl+option+command+/` shortcut is the terminal natural-language-to-shell flow. It is not currently bound in the checked-in `init.lua` Hammerspoon file.

## Binding Chain

1. Ghostty maps the physical shortcut to a private escape sequence:

   ```text
   ~/.config/ghostty/config
   keybind = ctrl+opt+cmd+/=text:\x1b[999;1u
   ```

2. `~/.zshrc` sources the widget file at shell startup:

   ```zsh
   [[ -r "$ZSH/widgets/codex-nl-shell.zsh" ]] && source "$ZSH/widgets/codex-nl-shell.zsh"
   ```

3. `~/.zsh/widgets/codex-nl-shell.zsh` binds that escape sequence to the zle widget:

   ```zsh
   local seq=$'\e[999;1u'
   bindkey "$seq" codex-nl-shell
   bindkey -M emacs "$seq" codex-nl-shell
   bindkey -M viins "$seq" codex-nl-shell
   bindkey -M vicmd "$seq" codex-nl-shell
   ```

## What It Does

1. You type a natural-language shell request at the zsh prompt, for example:

   ```text
   find the 20 largest json files under this repo
   ```

2. Press `ctrl+option+command+/` in Ghostty.
3. Ghostty sends `ESC [999;1u` into the terminal.
4. zsh runs the `codex-nl-shell` widget.
5. The widget trims the current prompt buffer and strips a leading `# ` if present.
6. It invokes Codex CLI:

   ```bash
   codex exec --ephemeral --sandbox read-only --skip-git-repo-check -m "${CODEX_NL_MODEL:-gpt-5.4-mini}" --cd "$PWD" -o "$tmp" "<conversion prompt>"
   ```

7. Codex returns one zsh command only.
8. The widget replaces your current command line with that generated command and leaves it there for review.
9. You press Enter only if the generated command looks right.

The shortcut does not execute the generated command automatically.

## Troubleshooting

- If the shell says `codex: type a shell request first`, the prompt buffer was empty.
- If it says `codex: CLI not found`, `codex` is not on `PATH`.
- If it fails, stderr is copied to `/tmp/codex-nl-shell-last.err`.
- If the shortcut does nothing, confirm Ghostty has the `ctrl+opt+cmd+/` keybind and zsh has sourced `~/.zsh/widgets/codex-nl-shell.zsh`.

## Related Hammerspoon Bindings

The Hammerspoon configs I found bind `ctrl+option+command+\` for older text-processing flows. The slash shortcut above is implemented through Ghostty plus zsh key bindings.
