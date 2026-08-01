/// NSImageExtension.swift

import Cocoa

extension NSImage {
    func rotated(by degrees: CGFloat) -> NSImage {
        let sinDegrees = abs(sin(degrees * CGFloat.pi / 180.0))
        let cosDegrees = abs(cos(degrees * CGFloat.pi / 180.0))
        let newSize = CGSize(width: size.height * sinDegrees + size.width * cosDegrees,
                             height: size.width * sinDegrees + size.height * cosDegrees)

        let imageBounds = NSRect(x: (newSize.width - size.width) / 2,
                                 y: (newSize.height - size.height) / 2,
                                 width: size.width, height: size.height)

        let otherTransform = NSAffineTransform()
        otherTransform.translateX(by: newSize.width / 2, yBy: newSize.height / 2)
        otherTransform.rotate(byDegrees: degrees)
        otherTransform.translateX(by: -newSize.width / 2, yBy: -newSize.height / 2)

        let rotatedImage = NSImage(size: newSize)
        rotatedImage.lockFocus()
        otherTransform.concat()
        draw(in: imageBounds, from: CGRect.zero, operation: NSCompositingOperation.copy, fraction: 1.0)
        rotatedImage.unlockFocus()

        return rotatedImage
    }

    func centeredSquareScaled(to dimension: CGFloat) -> NSImage {
        guard size.width > 0, size.height > 0, dimension > 0 else {
            let fallbackDimension = max(CGFloat(1), dimension)
            return NSImage(size: NSSize(width: fallbackDimension, height: fallbackDimension))
        }
        let sourceSide = min(size.width, size.height)
        let sourceRect = NSRect(
            x: max(0, (size.width - sourceSide) / 2),
            y: max(0, (size.height - sourceSide) / 2),
            width: sourceSide,
            height: sourceSide
        )
        let targetRect = NSRect(x: 0, y: 0, width: dimension, height: dimension)
        let scaledImage = NSImage(size: targetRect.size)
        scaledImage.lockFocus()
        draw(in: targetRect, from: sourceRect, operation: .sourceOver, fraction: 1.0)
        scaledImage.unlockFocus()
        return scaledImage
    }

    func scaledToFit(maxWidth: CGFloat, maxHeight: CGFloat) -> NSImage {
        guard size.width > 0, size.height > 0, maxWidth > 0, maxHeight > 0 else {
            return NSImage()
        }
        let scale = min(maxWidth / size.width, maxHeight / size.height, 1.0)
        let targetSize = NSSize(width: size.width * scale, height: size.height * scale)
        let targetRect = NSRect(origin: .zero, size: targetSize)
        let scaledImage = NSImage(size: targetSize)
        scaledImage.lockFocus()
        draw(in: targetRect, from: .zero, operation: .sourceOver, fraction: 1.0)
        scaledImage.unlockFocus()
        return scaledImage
    }
}

enum CustomLogoViewFactory {
    private static let panelIdentifier = NSUserInterfaceItemIdentifier("CustomBrandLogoPanel")

    static func installBrandPanel(in parentView: NSView) {
        guard descendant(with: panelIdentifier, in: parentView) == nil,
              let logo = NSImage(named: "CustomAppLogo")?.scaledToFit(maxWidth: 176, maxHeight: 44),
              let stackView = primaryVerticalStack(in: parentView) else {
            return
        }

        let panel = NSView()
        panel.identifier = panelIdentifier
        panel.wantsLayer = true
        panel.layer?.backgroundColor = NSColor(red: 0.067, green: 0.094, blue: 0.145, alpha: 1).cgColor
        panel.layer?.cornerRadius = 6
        panel.translatesAutoresizingMaskIntoConstraints = false

        let imageView = NSImageView(image: logo)
        imageView.imageScaling = .scaleProportionallyDown
        imageView.translatesAutoresizingMaskIntoConstraints = false
        panel.addSubview(imageView)

        NSLayoutConstraint.activate([
            panel.widthAnchor.constraint(equalToConstant: 196),
            panel.heightAnchor.constraint(equalToConstant: 56),
            imageView.centerXAnchor.constraint(equalTo: panel.centerXAnchor),
            imageView.centerYAnchor.constraint(equalTo: panel.centerYAnchor),
            imageView.widthAnchor.constraint(lessThanOrEqualToConstant: 176),
            imageView.heightAnchor.constraint(lessThanOrEqualToConstant: 44)
        ])

        stackView.insertArrangedSubview(panel, at: 0)
        stackView.setCustomSpacing(14, after: panel)
    }

    private static func primaryVerticalStack(in view: NSView) -> NSStackView? {
        let stacks = descendantStackViews(in: view)
            .filter { $0.orientation == .vertical && $0.arrangedSubviews.count > 1 }
        return stacks.max { $0.frame.height < $1.frame.height }
    }

    private static func descendant(with identifier: NSUserInterfaceItemIdentifier, in view: NSView) -> NSView? {
        for subview in view.subviews {
            if subview.identifier == identifier {
                return subview
            }
            if let match = descendant(with: identifier, in: subview) {
                return match
            }
        }
        return nil
    }

    private static func descendantStackViews(in view: NSView) -> [NSStackView] {
        var stacks = [NSStackView]()
        for subview in view.subviews {
            if let stack = subview as? NSStackView {
                stacks.append(stack)
            }
            stacks.append(contentsOf: descendantStackViews(in: subview))
        }
        return stacks
    }
}
