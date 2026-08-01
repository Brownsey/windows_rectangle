#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
source_dir="$script_dir/Rectangle"
derived_data="$script_dir/build"
release_dir="$script_dir/exe"
logo_dir="$repo_root/logo"
assets_dir="$source_dir/Rectangle/Assets.xcassets"
app_iconset="$source_dir/Rectangle/Assets.xcassets/AppIcon.appiconset"
app_iconset_backup="$derived_data/AppIcon.appiconset.backup"
custom_assets_backup="$derived_data/CustomLogoAssets.backup"
app_logo_imageset="$assets_dir/CustomAppLogo.imageset"
tray_logo_imageset="$assets_dir/CustomTrayLogo.imageset"
custom_iconset="$logo_dir/mac/AppIcon.appiconset"
custom_image=""
custom_tray_image=""

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

if [[ -f "$logo_dir/mac/tray_logo.png" ]]; then
  custom_tray_image="$logo_dir/mac/tray_logo.png"
elif [[ -f "$logo_dir/mac/tray_logo.webp" ]]; then
  custom_tray_image="$logo_dir/mac/tray_logo.webp"
elif [[ -f "$logo_dir/tray_logo.png" ]]; then
  custom_tray_image="$logo_dir/tray_logo.png"
elif [[ -f "$logo_dir/tray_logo.webp" ]]; then
  custom_tray_image="$logo_dir/tray_logo.webp"
fi

restore_app_iconset() {
  if [[ -d "$app_iconset_backup" ]]; then
    rm -rf "$app_iconset"
    cp -R "$app_iconset_backup" "$app_iconset"
  fi
}

restore_custom_logo_assets() {
  rm -rf "$app_logo_imageset" "$tray_logo_imageset"
  if [[ -d "$custom_assets_backup/CustomAppLogo.imageset" ]]; then
    cp -R "$custom_assets_backup/CustomAppLogo.imageset" "$app_logo_imageset"
  fi
  if [[ -d "$custom_assets_backup/CustomTrayLogo.imageset" ]]; then
    cp -R "$custom_assets_backup/CustomTrayLogo.imageset" "$tray_logo_imageset"
  fi
}

generate_icon_png() {
  local size="$1"
  local output="$2"

  sips -z "$size" "$size" "$custom_image" --out "$output" >/dev/null
}

generate_image_asset() {
  local image_name="$1"
  local source_image="$2"
  local output_dir="$3"
  local output_file="$output_dir/$image_name.png"

  if ! command -v sips >/dev/null 2>&1; then
    echo "sips is required to generate macOS image assets from $source_image" >&2
    exit 1
  fi

  rm -rf "$output_dir"
  mkdir -p "$output_dir"
  sips -Z 512 "$source_image" --out "$output_file" >/dev/null
  cat > "$output_dir/Contents.json" <<EOF
{
  "images" : [
    {
      "filename" : "$image_name.png",
      "idiom" : "universal"
    }
  ],
  "info" : {
    "author" : "xcode",
    "version" : 1
  }
}
EOF
}

apply_custom_logo_assets() {
  rm -rf "$custom_assets_backup"
  mkdir -p "$custom_assets_backup"
  if [[ -d "$app_logo_imageset" ]]; then
    cp -R "$app_logo_imageset" "$custom_assets_backup/CustomAppLogo.imageset"
  fi
  if [[ -d "$tray_logo_imageset" ]]; then
    cp -R "$tray_logo_imageset" "$custom_assets_backup/CustomTrayLogo.imageset"
  fi

  if [[ -n "$custom_image" ]]; then
    echo "Generating macOS Preferences logo asset from $custom_image"
    generate_image_asset "CustomAppLogo" "$custom_image" "$app_logo_imageset"
  fi

  if [[ -n "$custom_tray_image" ]]; then
    echo "Generating macOS menu bar icon asset from $custom_tray_image"
    generate_image_asset "CustomTrayLogo" "$custom_tray_image" "$tray_logo_imageset"
  fi
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

trap 'restore_app_iconset; restore_custom_logo_assets' EXIT

rm -rf "$release_dir"
mkdir -p "$release_dir"
mkdir -p "$derived_data"

apply_custom_logo
apply_custom_logo_assets

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
