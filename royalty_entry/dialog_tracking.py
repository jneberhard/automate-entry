"""Locate the topmost License Manager dialog independently of its parent."""
import math
from .paths import asset_root
from .tracking import ViewTransform, TrackingError

class DialogTracker:
    anchors = (
        ('chooser', (699,245)),
        ('entry', (788,408)),
        ('financials', (498,223)),
        ('properties', (773,252)),
    )

    def __init__(self):
        import cv2
        self.cv = cv2
        self.templates = [(name,anchor,cv2.imread(str(asset_root()/'assets'/f'dialog-{name}.png'),cv2.IMREAD_GRAYSCALE))
                          for name,anchor in self.anchors]
        if any(template is None for _,_,template in self.templates):
            raise TrackingError('A License Manager dialog tracking image is missing')

    def locate(self, image, scale_hint=None):
        import numpy as np
        gray = self.cv.cvtColor(np.asarray(image.convert('RGB')),self.cv.COLOR_RGB2GRAY)
        if scale_hint is None:
            scales = [1.0] + [1.035**n for n in range(math.floor(math.log(.25,1.035)),math.ceil(math.log(2.5,1.035))+1)]
        else:
            scales = [scale_hint*(1+step*.004) for step in (0,-1,1,-2,2)]
        # Nested forms take priority over any visible parent title behind them.
        for name,anchor,template in self.templates:
            best = None
            checked = set()
            for scale in scales:
                w,h = round(template.shape[1]*scale),round(template.shape[0]*scale)
                if (w,h) in checked or min(w,h)<8 or w>gray.shape[1] or h>gray.shape[0]:continue
                checked.add((w,h))
                resized = self.cv.resize(template,(w,h),interpolation=self.cv.INTER_AREA if scale<1 else self.cv.INTER_CUBIC)
                scores = self.cv.matchTemplate(gray,resized,self.cv.TM_CCOEFF_NORMED)
                _,score,_,position = self.cv.minMaxLoc(scores)
                if best is None or score>best[0]:best=(score,position,w,h,scores)
                if score>=.98:break
            if best is None or best[0]<.88:continue
            score,(x,y),w,h,scores=best
            scores[max(0,y-h//2):y+h//2+1,max(0,x-w//2):x+w//2+1]=-1
            if score-float(scores.max())<.04:
                raise TrackingError(f'More than one matching {name} dialog is visible')
            scale=w/template.shape[1]
            return ViewTransform(scale,x-scale*anchor[0],y-scale*anchor[1],score),anchor
        return None
