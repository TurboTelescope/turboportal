#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

SECRET_FILE="config/docker.yaml"
ENC_FILE="config/docker.yaml.age"
IDENTITY="$HOME/.ssh/turbo"
RECIPIENT="$HOME/.ssh/turbo.pub"

if ! command -v age >/dev/null 2>&1; then
  echo "age not found; install it (e.g. apt-get install age) before continuing" >&2
  exit 1
fi

decrypt() {
  age -d -i "$IDENTITY" -o "$SECRET_FILE" "$ENC_FILE"
  chmod 600 "$SECRET_FILE"
}

# Initial decrypt if the plaintext is missing or stale relative to the ciphertext.
if [ -f "$ENC_FILE" ] && { [ ! -f "$SECRET_FILE" ] || [ "$ENC_FILE" -nt "$SECRET_FILE" ]; }; then
  decrypt
fi

HOOKS_DIR="$(git rev-parse --git-path hooks)"
mkdir -p "$HOOKS_DIR"

cat > "$HOOKS_DIR/pre-commit" <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
SECRET_FILE="config/docker.yaml"
ENC_FILE="config/docker.yaml.age"
IDENTITY="$HOME/.ssh/turbo"
RECIPIENT="$HOME/.ssh/turbo.pub"

# Hard refuse: never allow the plaintext secret file itself into a commit,
# even if someone force-adds it past .gitignore.
if git diff --cached --name-only | grep -qx "$SECRET_FILE"; then
  echo "refusing commit: $SECRET_FILE (plaintext) is staged directly" >&2
  exit 1
fi

if [ -f "$SECRET_FILE" ]; then
  TMP="$(mktemp)"
  trap 'rm -f "$TMP"' EXIT
  if [ -f "$ENC_FILE" ] && git cat-file -e "HEAD:$ENC_FILE" 2>/dev/null; then
    # Compare against the COMMITTED ciphertext, not the working-tree one --
    # a working-tree comparison can go stale after a manual hook run + reset.
    git show "HEAD:$ENC_FILE" | age -d -i "$IDENTITY" -o "$TMP"
    if cmp -s "$TMP" "$SECRET_FILE"; then
      exit 0
    fi
  fi
  age -R "$RECIPIENT" -o "$ENC_FILE" "$SECRET_FILE"
  git add "$ENC_FILE"
fi
HOOK
chmod +x "$HOOKS_DIR/pre-commit"

cat > "$HOOKS_DIR/post-merge" <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
SECRET_FILE="config/docker.yaml"
ENC_FILE="config/docker.yaml.age"
IDENTITY="$HOME/.ssh/turbo"
if [ -f "$ENC_FILE" ] && { [ ! -f "$SECRET_FILE" ] || [ "$ENC_FILE" -nt "$SECRET_FILE" ]; }; then
  age -d -i "$IDENTITY" -o "$SECRET_FILE" "$ENC_FILE"
  chmod 600 "$SECRET_FILE"
fi
HOOK
chmod +x "$HOOKS_DIR/post-merge"

echo "Secrets decrypted (if needed) and git hooks installed."
