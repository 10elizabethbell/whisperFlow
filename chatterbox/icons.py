"""Menu-bar logo: a circle with a wave running through it.

Drawn with NSBezierPath into a template image (monochrome; macOS tints
it for light/dark menu bars and menu-open highlight). Rendered at 2x
(36px) and sized to 18pt for retina crispness.

State variants:
    loading    faint outline
    idle       outline
    recording  filled disc, wave knocked out (bold = live mic)
    processing dimmed filled disc
"""

from __future__ import annotations

from AppKit import (
    NSBezierPath,
    NSColor,
    NSCompositingOperationDestinationOut,
    NSGraphicsContext,
    NSImage,
    NSMakeRect,
)

PX = 36.0  # backing pixels (2x of 18pt)
INSET = 2.0  # keep the stroke inside the canvas
LINE = 2.4  # stroke width at 2x

# wave control points in unit space (0..1 across the circle's bounding
# box, y-up), eyeballed from the reference: enters mid-left, dips to a
# trough, tight bump over center, long tail exiting lower-right
WAVE = [
    # (to, ctrl1, ctrl2)
    ((0.35, 0.37), (0.13, 0.44), (0.24, 0.37)),
    ((0.53, 0.56), (0.46, 0.37), (0.45, 0.56)),
    ((0.94, 0.27), (0.62, 0.56), (0.75, 0.40)),
]
WAVE_START = (0.005, 0.49)


def _unit_to_px(p: tuple[float, float]) -> tuple[float, float]:
    span = PX - 2 * INSET
    return (INSET + p[0] * span, INSET + p[1] * span)


def _wave_path() -> NSBezierPath:
    path = NSBezierPath.bezierPath()
    path.moveToPoint_(_unit_to_px(WAVE_START))
    for to, c1, c2 in WAVE:
        path.curveToPoint_controlPoint1_controlPoint2_(
            _unit_to_px(to), _unit_to_px(c1), _unit_to_px(c2)
        )
    path.setLineWidth_(LINE)
    return path


def _circle_path() -> NSBezierPath:
    rect = NSMakeRect(INSET, INSET, PX - 2 * INSET, PX - 2 * INSET)
    path = NSBezierPath.bezierPathWithOvalInRect_(rect)
    path.setLineWidth_(LINE)
    return path


def logo(state: str) -> NSImage:
    image = NSImage.alloc().initWithSize_((PX, PX))
    image.lockFocus()
    try:
        alpha = {"loading": 0.35, "processing": 0.45}.get(state, 1.0)
        color = NSColor.blackColor().colorWithAlphaComponent_(alpha)
        if state in ("recording", "processing"):
            color.setFill()
            _circle_path().fill()
            # knock the wave out of the filled disc
            NSGraphicsContext.currentContext().setCompositingOperation_(
                NSCompositingOperationDestinationOut
            )
            NSColor.blackColor().setStroke()
            wave = _wave_path()
            wave.setLineWidth_(LINE + 0.6)
            wave.stroke()
        else:
            color.setStroke()
            _circle_path().stroke()
            _wave_path().stroke()
    finally:
        image.unlockFocus()
    image.setSize_((18.0, 18.0))
    image.setTemplate_(True)
    return image
