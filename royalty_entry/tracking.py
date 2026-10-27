"""Locate a graphical landmark and map logical and displayed pixels together."""
from dataclasses import dataclass
import math
from .paths import asset_root


class TrackingError(RuntimeError):
    pass


@dataclass(frozen=True)
class ViewTransform:
    scale: float
    x: float
    y: float
    score: float = 1.0

    def point(self, x, y):
        return round(self.x+self.scale*x), round(self.y+self.scale*y)

    def normalize(self, image, size):
        from PIL import Image
        return image.transform(tuple(size), Image.Transform.AFFINE,
                               (self.scale, 0, self.x, 0, self.scale, self.y),
                               resample=Image.Resampling.BICUBIC)

    def native_pixels(self, anchor):
        """Preserve native 1:1 glyphs instead of resampling fractional fit noise."""
        if abs(self.scale-1) < .01:
            left, top = self.point(*anchor)
            return ViewTransform(1, left-anchor[0], top-anchor[1], self.score)
        return self


class ToolbarTracker:
    reference = (447, 153)

    def __init__(self, path=None):
        import cv2
        self.cv = cv2
        self.template = cv2.imread(str(path or asset_root()/'assets'/'license-toolbar.png'), cv2.IMREAD_GRAYSCALE)
        if self.template is None:
            raise TrackingError('The License Manager tracking template is missing')
        self.previous = None

    def locate(self, image):
        import numpy as np
        gray = self.cv.cvtColor(np.asarray(image.convert('RGB')), self.cv.COLOR_RGB2GRAY)
        best = None
        checked = set()

        def test(scale, roi=None):
            nonlocal best
            width = round(self.template.shape[1]*scale)
            height = round(self.template.shape[0]*scale)
            if min(width, height) < 8 or width > gray.shape[1] or height > gray.shape[0]:
                return
            key = (width, height, roi)
            if key in checked:
                return
            checked.add(key)
            resized = self.cv.resize(self.template, (width, height),
                                     interpolation=self.cv.INTER_AREA if scale < 1 else self.cv.INTER_CUBIC)
            left, top, right, bottom = roi or (0, 0, gray.shape[1], gray.shape[0])
            if right-left < width or bottom-top < height:
                return
            scores = self.cv.matchTemplate(gray[top:bottom, left:right], resized, self.cv.TM_CCOEFF_NORMED)
            _, score, _, location = self.cv.minMaxLoc(scores)
            remaining = scores.copy()
            rx, ry = location
            remaining[max(0, ry-height//2):min(remaining.shape[0], ry+height//2+1),
                      max(0, rx-width//2):min(remaining.shape[1], rx+width//2+1)] = -1
            _, runner_up, _, runner_location = self.cv.minMaxLoc(remaining)
            measured_scale = width/self.template.shape[1]
            result = (score, measured_scale, location[0]+left, location[1]+top, width, height,
                      runner_up, (runner_location[0]+left, runner_location[1]+top))
            if best is None or result[0] > best[0]:
                best = result

        if self.previous:
            old = self.previous
            px, py = old.point(*self.reference)
            width = round(self.template.shape[1]*old.scale)
            height = round(self.template.shape[0]*old.scale)
            roi = (max(0, px-5), max(0, py-5), min(gray.shape[1], px+width+5), min(gray.shape[0], py+height+5))
            test(old.scale, roi)
            if best and best[0] >= 0.90:
                return self._finish(best)
        for exponent in range(math.floor(math.log(.25, 1.035)), math.ceil(math.log(2.5, 1.035))+1):
            test(1.035**exponent)
        if best:
            center = best[1]
            for step in range(-14, 15):
                test(center+step/(4*self.template.shape[1]))
        if best is None or best[0] < 0.78:
            raise TrackingError('Could not reliably locate the License Manager toolbar in the scaled view. '
                                'Bring License Manager to the front inside Remote Desktop, with its toolbar visible, and retry.')
        if best[0]-best[6] < .04:
            # The long gray/black gradient also occurs on unrelated toolbars
            # and blank areas. Similar shading alone is not a second toolbar.
            _, _, left, top, width, height, _, runner = best
            primary = self._icon_pattern(gray, (left, top), width, height)
            secondary = self._icon_pattern(gray, runner, width, height)
            if not primary:
                raise TrackingError('The License Manager toolbar icon pattern could not be verified. Keep its complete toolbar visible and retry.')
            if secondary:
                raise TrackingError('More than one matching License Manager toolbar is visible. Keep only the intended window in view.')
        return self._finish(best)

    def _icon_pattern(self, gray, position, width, height):
        """Require icon edges throughout the toolbar, independent of shading."""
        import numpy as np
        left, top = position
        candidate = gray[top:top+height, left:left+width]
        if candidate.shape != (height, width):
            return False
        template = self.cv.resize(self.template, (width, height),
            interpolation=self.cv.INTER_AREA if width < self.template.shape[1] else self.cv.INTER_CUBIC)
        expected = self.cv.Canny(template, 50, 120)
        actual = self.cv.dilate(self.cv.Canny(candidate, 50, 120), np.ones((3,3), dtype=np.uint8))
        for start, end in zip((0, width//3, 2*width//3), (width//3, 2*width//3, width)):
            mask = expected[:,start:end] > 0
            if not mask.any() or (actual[:,start:end][mask] > 0).mean() < .55:
                return False
        return True

    def _finish(self, result):
        score, scale, left, top = result[:4]
        self.previous = ViewTransform(scale, left-scale*self.reference[0], top-scale*self.reference[1], score)
        return self.previous
