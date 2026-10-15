"""Draw the source bitmap at its physical size; text and page layout stay separate."""
from reportlab.lib.utils import ImageReader


def draw_background(canvas, image, coordinate_width, coordinate_height):
    canvas.saveState()
    canvas.translate(0, coordinate_height)
    canvas.scale(1, -1)
    canvas.drawImage(ImageReader(image), 0, 0, coordinate_width, coordinate_height)
    canvas.restoreState()
