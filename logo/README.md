# Custom Logo Assets

Place custom logo files in this folder before building release artifacts.

## Windows

The Windows Preferences UI loads the first matching app logo in this order:

```text
logo/windows.ico
logo/logo.ico
logo/app.ico
logo/windows.png
logo/logo.png
logo/app.png
logo/windows.webp
logo/logo.webp
logo/app.webp
```

The Windows system tray icon loads only these files, in this order:

```text
logo/tray_logo.ico
logo/tray_logo.png
logo/tray_logo.webp
```

Use an `.ico` file when you want the generated `WindowsRectangle.exe` itself to
have the custom icon. Use `tray_logo.ico`, `tray_logo.png`, or
`tray_logo.webp` for the system tray icon. If no tray-specific logo exists, the
tray uses a transparent blank icon. PNG and WebP `logo.*` files are used by the
Preferences window. Rebuild Windows release artifacts after changing files in
this folder.

## macOS

The macOS build script supports either:

```text
logo/mac/AppIcon.appiconset
```

or:

```text
logo/mac/logo.png
logo/mac/logo.webp
logo/logo.png
logo/logo.webp
```

The macOS menu bar icon uses a tray-specific file, in this order:

```text
logo/mac/tray_logo.png
logo/mac/tray_logo.webp
logo/tray_logo.png
logo/tray_logo.webp
```

When a PNG or WebP is provided, `apps/mac/build-release.sh` uses macOS `sips` to
create the required app icon sizes and temporary Preferences/menu bar image
assets before building. A 1024x1024 PNG is recommended for the widest tooling
compatibility. If no tray logo exists, the macOS menu bar icon uses a
transparent blank image.
