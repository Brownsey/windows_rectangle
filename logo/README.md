# Custom Logo Assets

Place custom logo files in this folder before building release artifacts.

## Windows

The Windows app loads the first matching file in this order:

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

Use an `.ico` file when you want the generated `WindowsRectangle.exe` itself to
have the custom icon. PNG and WebP files are used by the tray and Preferences
UI.

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

When a PNG or WebP is provided, `apps/mac/build-release.sh` uses macOS `sips` to
create the required app icon sizes before building. A 1024x1024 PNG is
recommended for the widest tooling compatibility.
