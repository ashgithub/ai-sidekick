# Codex NL-to-Shell Shortcut

The `ctrl+option+command+/` shortcut is the terminal natural-language-to-shell flow. It is separate from the Hammerspoon `ctrl+option+command+\` AI Text Tools shortcut, which opens Ask mode for Terminal, iTerm2, Ghostty, Codex, Code, Safari, and Chrome through `/api/shortcut`.

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
6. It invokes the resident sidekick-backed helper:

   ```bash
   /Users/ashish/work/code/python/ai_tools/bin/codex-nl-shell "$query"
   ```

7. The helper submits a zsh command-generation task to the resident bridge and waits for one command.
8. The widget replaces your current command line with that generated command and leaves it there for review.
9. You press Enter only if the generated command looks right.

The shortcut does not execute the generated command automatically.

## Troubleshooting

- If the shell says `codex: type a shell request first`, the prompt buffer was empty.
- If it says `codex: sidekick helper not found`, confirm the repo exists at `~/work/code/python/ai_tools`.
- If it says `codex: sidekick failed`, start `./bin/sidekick --restart` and check `/tmp/codex-nl-shell-last.err`.
- If the shortcut does nothing, confirm Ghostty has the `ctrl+opt+cmd+/` keybind and zsh has sourced `~/.zsh/widgets/codex-nl-shell.zsh`.

## Related Hammerspoon Bindings

The Hammerspoon configs bind `ctrl+option+command+\` for AI text submissions into the sidekick. The slash shortcut above is implemented through Ghostty plus zsh key bindings.
