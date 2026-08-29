# macOS App

This folder contains the macOS app.

`Rectangle/` is a vendored fork snapshot of
<https://github.com/rxhanson/Rectangle> at commit
`6cfcb4720b3a6f83df82a8896a3da4751e90ca4e`.

The copied Rectangle source is intentionally left unchanged. Repository-specific
build notes live beside it in this folder.

## Requirements

- macOS with Xcode installed.
- Xcode command line tools available through `xcodebuild`.
- Accessibility permission granted to the built app the first time it runs.

This app cannot be built on Windows because it depends on Apple's Xcode toolchain.

## Run Locally

From the repository root on macOS:

```bash
bash build-mac-release.sh
open apps/mac/build/Build/Products/Release/Rectangle.app
```

The first launch will require macOS Accessibility permission:

```text
System Settings > Privacy & Security > Accessibility
```

Enable the built Rectangle app there, then restart the app if macOS asks you to.

## Build A Shareable Zip

The macOS release build must be run on a Mac with Xcode installed. From a fresh
checkout on the Mac:

```bash
git pull
xcode-select --install
```

If Xcode is already installed, `xcode-select --install` may report that the
tools are already present; that is fine.

Place the optional logo assets before building:

```text
logo/mac/logo.png          # Preferences UI, Dock/app icon source
logo/mac/tray_logo.png     # macOS menu bar icon
```

Root-level fallbacks also work:

```text
logo/logo.png
logo/tray_logo.png
```

Build from the repository root:

```bash
bash build-mac-release.sh
```

Or from this folder:

```bash
bash build-release.sh
```

The script builds the `Rectangle` Xcode scheme in Release mode and creates:

```text
apps/mac/exe/Rectangle-macOS.zip
apps/mac/exe/Rectangle-macOS.zip.sha256
```

The built app also remains available locally at:

```text
apps/mac/build/Build/Products/Release/Rectangle.app
```

To test it locally:

```bash
open apps/mac/build/Build/Products/Release/Rectangle.app
```

For the first launch, grant Accessibility access when macOS asks:

```text
System Settings > Privacy & Security > Accessibility
```

By default the script disables code signing so local CI or a developer machine
can produce a test artifact. For a downloadable production build, provide a
valid Apple Developer signing setup and notarize the app.

Example signed build shape:

```bash
CODE_SIGNING_ALLOWED=YES \
DEVELOPMENT_TEAM=<TEAM_ID> \
CODE_SIGN_IDENTITY="Developer ID Application: Your Company" \
bash build-mac-release.sh
```

Notarization and stapling should be handled by your release process after the
zip is produced.

This repository currently builds a shareable `.zip`, not a `.pkg` or `.dmg`
installer. The zip contains `Rectangle.app`; users can extract it and move the
app into `/Applications`.

## Custom Logo

Place custom logo files in the repository root `logo` folder before building.

Preferred macOS option:

```text
logo/mac/AppIcon.appiconset
```

Simple PNG option:

```text
logo/mac/logo.png
logo/mac/logo.webp
logo/logo.png
logo/logo.webp
```

Menu bar icon option:

```text
logo/mac/tray_logo.png
logo/mac/tray_logo.webp
logo/tray_logo.png
logo/tray_logo.webp
```

Use a 1024x1024 PNG or WebP for the app icon/logo simple option. PNG is
preferred for the widest macOS tooling compatibility. During
`build-release.sh`, the script uses macOS `sips` to generate the required app
icon sizes, applies a visible Preferences logo asset, and applies a dedicated
menu bar icon asset. The build prefers `logo/mac/*` files and falls back to the
root `logo/*` files. If no tray logo exists, the macOS menu bar icon uses a
transparent blank image. The script restores the original vendored icon assets
before exiting.

## ISO Build Note

The Rectangle application source is vendored here rather than pulled from
upstream during the release build.

The Xcode project still declares Swift Package Manager dependencies:

- `rxhanson/MASShortcut`, pinned in the Xcode project to revision
  `2f9fbb3f959b7a683c6faaf9638d22afad37a235`
- `sparkle-project/Sparkle`, declared as version `2.0.0` up to the next major
  version by the upstream project

For a fully hermetic ISO release process, mirror or vendor those dependencies
inside your trusted source boundary and commit the resolved dependency state
from a trusted macOS build host.
