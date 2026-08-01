#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
source_dir="$script_dir/Rectangle"
derived_data="$script_dir/build"
release_dir="$script_dir/exe"
logo_dir="$repo_root/logo"
app_iconset="$source_dir/Rectangle/Assets.xcassets/AppIcon.appiconset"
app_iconset_backup="$derived_data/AppIcon.appiconset.backup"
custom_iconset="$logo_dir/mac/AppIcon.appiconset"
custom_image=""

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "macOS release builds must run on macOS with Xcode installed." >&2
  exit 1
fi

if [[ -f "$logo_dir/mac/logo.png" ]]; then
  custom_image="$logo_dir/mac/logo.png"
elif [[ -f "$logo_dir/mac/logo.webp" ]]; then
  custom_image="$logo_dir/mac/logo.webp"
elif [[ -f "$logo_dir/logo.png" ]]; then
  custom_image="$logo_dir/logo.png"
elif [[ -f "$logo_dir/logo.webp" ]]; then
  custom_image="$logo_dir/logo.webp"
fi

restore_app_iconset() {
  if [[ -d "$app_iconset_backup" ]]; then
    rm -rf "$app_iconset"
    cp -R "$app_iconset_backup" "$app_iconset"
  fi
}

generate_icon_png() {
  local size="$1"
  local output="$2"

  sips -z "$size" "$size" "$custom_image" --out "$output" >/dev/null
}

apply_custom_logo() {
  if [[ -d "$custom_iconset" ]]; then
    echo "Applying custom macOS iconset from $custom_iconset"
    rm -rf "$app_iconset_backup"
    cp -R "$app_iconset" "$app_iconset_backup"
    rm -rf "$app_iconset"
    cp -R "$custom_iconset" "$app_iconset"
    return
  fi

  if [[ -n "$custom_image" ]]; then
    if ! command -v sips >/dev/null 2>&1; then
      echo "sips is required to generate a macOS iconset from $custom_image" >&2
      exit 1
    fi

    echo "Generating macOS iconset from $custom_image"
    rm -rf "$app_iconset_backup"
    cp -R "$app_iconset" "$app_iconset_backup"
    generate_icon_png 16 "$app_iconset/mac016pts1x.png"
    generate_icon_png 32 "$app_iconset/mac016pts2x.png"
    generate_icon_png 32 "$app_iconset/mac032pts1x.png"
    generate_icon_png 64 "$app_iconset/mac032pts2x.png"
    generate_icon_png 128 "$app_iconset/mac128pts1x.png"
    generate_icon_png 256 "$app_iconset/mac128pts2x.png"
    generate_icon_png 256 "$app_iconset/mac256pts1x.png"
    generate_icon_png 512 "$app_iconset/mac256pts2x.png"
    generate_icon_png 512 "$app_iconset/mac512pts1x.png"
    generate_icon_png 1024 "$app_iconset/mac512pts2x.png"
  fi
}

trap restore_app_iconset EXIT

rm -rf "$release_dir"
mkdir -p "$release_dir"
mkdir -p "$derived_data"

apply_custom_logo

xcodebuild \
  -project "$source_dir/Rectangle.xcodeproj" \
  -scheme Rectangle \
  -configuration Release \
  -derivedDataPath "$derived_data" \
  CODE_SIGNING_ALLOWED="${CODE_SIGNING_ALLOWED:-NO}"

app_path="$derived_data/Build/Products/Release/Rectangle.app"
zip_path="$release_dir/Rectangle-macOS.zip"
checksum_path="$zip_path.sha256"

test -d "$app_path"
ditto -c -k --sequesterRsrc --keepParent "$app_path" "$zip_path"
shasum -a 256 "$zip_path" > "$checksum_path"

echo "$zip_path"
echo "$checksum_path"
