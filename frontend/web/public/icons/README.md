# Icons

This directory contains PWA icons for TeleBot.

## Required Files

- **icon-192.png**: 192x192px app icon (for mobile home screen)
- **icon-512.png**: 512x512px app icon (for splash screen)
- **favicon.ico**: 16x16px, 32x32px favicon (browser tab)

## Generation

You can generate these icons from a source SVG/PNG using:
- https://realfavicongenerator.net/
- https://www.pwabuilder.com/imageGenerator

## Design Guidelines

- Use the TeleBot logo (chart icon + brand colors)
- Ensure legibility at small sizes (192px)
- Use transparent or gold background (#d4941d)
- Follow PWA icon guidelines (safe zone for rounded corners)

## Temporary Placeholder

For development, you can use:
```bash
# Generate placeholder icons (requires ImageMagick)
convert -size 192x192 xc:#d4941d -pointsize 120 -fill white -gravity center -annotate +0+0 "TB" icon-192.png
convert -size 512x512 xc:#d4941d -pointsize 320 -fill white -gravity center -annotate +0+0 "TB" icon-512.png
```
