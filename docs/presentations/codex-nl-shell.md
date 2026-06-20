Codex NL-to-Shell
=================

Type English. Press the shortcut. Review the command.

```text
╭─ ghostty ~/work/code/python/ai_tools
╰─$ find the 20 largest markdown files under this repo

        press ctrl+option+command+/

╭─ ghostty ~/work/code/python/ai_tools
╰─$ fd -e md -x du -h {} | sort -hr | head -20
```

The generated command is inserted into your shell prompt. It is not executed until you press Enter.

<!-- end_slide -->

Live Sequence
=============

```mermaid
%%{init: {"theme": "base", "themeVariables": {"background": "#0f172a", "actorBkg": "#22d3ee", "actorBorder": "#67e8f9", "actorTextColor": "#082f49", "signalColor": "#facc15", "signalTextColor": "#fde68a", "activationBkgColor": "#a78bfa", "activationBorderColor": "#ddd6fe", "fontFamily": "JetBrains Mono"}}}%%
sequenceDiagram
    participant You
    participant Ghostty
    participant zsh
    participant Sidekick

    You->>Ghostty: type an English shell request
    You->>Ghostty: press ctrl+option+command+/
    Ghostty->>zsh: private escape sequence
    zsh->>Sidekick: bin/codex-nl-shell
    Sidekick-->>zsh: one safe zsh command
    zsh-->>You: command appears in BUFFER
    You->>zsh: review, edit, or press Enter
```

<!-- end_slide -->

Step 1: Ghostty Captures The Shortcut
=====================================

File: `~/.config/ghostty/config`

```text
# Codex NL-to-shell: Ctrl+Option+Command+/
keybind = ctrl+opt+cmd+/=text:\x1b[999;1u
```

What this means:

```text
ctrl+option+command+/  ->  ESC [999;1u
```

Ghostty turns the macOS key chord into a private terminal escape sequence.

<!-- end_slide -->

Step 2: zsh Loads The Widget
============================

File: `~/.zshrc`

```zsh
export ZSH="$HOME/.zsh"

# Codex NL-to-shell widget; keep last so it wins final keymap order.
[[ -r "$ZSH/widgets/codex-nl-shell.zsh" ]] && source "$ZSH/widgets/codex-nl-shell.zsh"
```

Why it is loaded last:

```text
other plugins bind keys first
codex-nl-shell binds last
the shortcut wins final keymap order
```

<!-- end_slide -->

Step 3: zle Binds The Escape Sequence
=====================================

File: `~/.zsh/widgets/codex-nl-shell.zsh`

```zsh
zle -N codex-nl-shell _codex_nl_shell

_codex_nl_shell_bindkeys() {
  local seq=$'\e[999;1u'

  bindkey "$seq" codex-nl-shell
  bindkey -M emacs "$seq" codex-nl-shell 2>/dev/null
  bindkey -M viins "$seq" codex-nl-shell 2>/dev/null
  bindkey -M vicmd "$seq" codex-nl-shell 2>/dev/null
}
```

The same shortcut works in emacs mode, vi insert mode, and vi command mode.

<!-- end_slide -->

Step 4: The Widget Reads Your Prompt
====================================

File: `~/.zsh/widgets/codex-nl-shell.zsh`

Plain-English version:

```text
1. Save whatever is currently typed at the prompt.
2. Treat the current prompt text as the English request.
3. Trim extra spaces from the beginning and end.
4. Optionally remove a leading "# " if you typed the request as a shell comment.
5. If nothing is left, show a message and stop.
6. Submit the request to the resident sidekick helper.
```

```zsh
original_buffer="$BUFFER"
query="$BUFFER"
query="${query#"${query%%[![:space:]]*}"}"
query="${query%"${query##*[![:space:]]}"}"
query="${query#\# }"

if [[ -z "$query" ]]; then
  zle -M "codex: type a shell request first"
  return 0
fi
```

The `# ` step is optional convenience, not core logic. It lets you type `# find large files` safely at a shell prompt.

<!-- end_slide -->

Step 5: The Sidekick Generates One Command
==========================================

File: `~/.zsh/widgets/codex-nl-shell.zsh`

```zsh
local helper="$HOME/work/code/python/ai_tools/bin/codex-nl-shell"

"$helper" "$query" >"$tmp" 2>"$err"
```

Important guardrails:

```text
resident Codex sidekick
configured model and sandbox policy
current directory context is included in the prompt
command only, no explanation
```

<!-- end_slide -->

Step 6: zsh Replaces The Buffer
===============================

File: `~/.zsh/widgets/codex-nl-shell.zsh`

Plain-English version:

```text
1. Read the command Codex wrote into the temp file.
2. Delete the temp output and error files.
3. Normalize line endings and trim extra whitespace.
4. Strip accidental Markdown fences if Codex included them.
5. Replace the current zsh prompt text with the command.
6. Move the cursor to the end and tell you to review before Enter.
```

```zsh
generated="$(<"$tmp")"
command rm -f "$tmp" "$err"

generated="${generated//$'\r'/}"
generated="${generated#"${generated%%[![:space:]]*}"}"
generated="${generated%"${generated##*[![:space:]]}"}"
generated="${generated#\`\`\`zsh$'\n'}"
generated="${generated#\`\`\`sh$'\n'}"
generated="${generated#\`\`\`bash$'\n'}"
generated="${generated#\`\`\`$'\n'}"
generated="${generated%$'\n'\`\`\`}"

BUFFER="$generated"
CURSOR=${#BUFFER}
zle -M "codex: command ready, review before Enter"
zle reset-prompt
```

The final safety step is human review. The command is visible before it runs.
