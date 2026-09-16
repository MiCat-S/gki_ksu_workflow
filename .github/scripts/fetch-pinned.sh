#!/usr/bin/env bash
set -euo pipefail

if (( $# < 3 )); then
  echo "Usage: fetch-pinned.sh DEST FULL_SHA URL [MIRROR_URL ...]" >&2
  exit 2
fi
dest=$1
sha=$2
shift 2
[[ $sha =~ ^[0-9a-f]{40}$ ]] || { echo "A full commit SHA is required" >&2; exit 1; }
[[ ! -e $dest ]] || { echo "Destination already exists: $dest" >&2; exit 1; }
mkdir -p "$(dirname "$dest")"
tmp=$(mktemp -d "${dest}.fetch.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
git init -q "$tmp"
fetch_options=(--no-tags --depth=1)
if [[ ${FETCH_FULL_HISTORY:-false} == true ]]; then
  fetch_options=(--tags)
fi
for url in "$@"; do
  if git -C "$tmp" fetch "${fetch_options[@]}" "$url" "$sha"; then
    actual=$(git -C "$tmp" rev-parse 'FETCH_HEAD^{commit}')
    [[ $actual == "$sha" ]] || { echo "Remote returned a different commit" >&2; exit 1; }
    git -C "$tmp" checkout -q --detach "$sha"
    git -C "$tmp" remote add origin "$url"
    mv "$tmp" "$dest"
    trap - EXIT
    exit 0
  fi
  echo "Fetch failed; trying the next mirror for the same commit $sha" >&2
done
echo "No mirror supplied the pinned commit $sha" >&2
exit 1
