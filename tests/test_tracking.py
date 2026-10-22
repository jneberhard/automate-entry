from pathlib import Path
import cv2
import numpy as np
import pytest
from PIL import Image
from royalty_entry.tracking import ToolbarTracker, TrackingError, ViewTransform


def test_native_reading_preserves_pixel_grid_despite_fractional_match_noise():
    view = ViewTransform(.9978, 447-.9978*447, 153-.9978*153)
    native = view.native_pixels((447, 153))
    assert native == ViewTransform(1, 0, 0)
    assert ViewTransform(.52, 5, 8).native_pixels((447, 153)).scale == .52


@pytest.mark.parametrize('scale', [.45, .52, .75, 1, 1.5])
def test_locates_scaled_toolbar_and_maps_distant_controls(scale):
    tracker = ToolbarTracker()
    template = tracker.template
    width = round(template.shape[1]*scale)
    height = round(template.shape[0]*scale)
    scene = np.full((1000, 1500), 235, dtype=np.uint8)
    resized = cv2.resize(template, (width, height), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    scene[90:90+height, 200:200+width] = resized
    view = tracker.locate(Image.fromarray(scene).convert('RGB'))
    assert abs(view.scale-scale) < .004
    anchor = view.point(*tracker.reference)
    assert abs(anchor[0]-200) <= 1 and abs(anchor[1]-90) <= 1
    actual = view.point(1394, 900)
    expected = (200+scale*(1394-447), 90+scale*(900-153))
    assert abs(actual[0]-expected[0]) < 4
    assert abs(actual[1]-expected[1]) < 4


def test_unknown_screen_and_duplicate_toolbars_are_rejected():
    tracker = ToolbarTracker()
    with pytest.raises(TrackingError):
        tracker.locate(Image.new('RGB', (1008, 711), 'white'))
    scene = Image.new('RGB', (1600, 800), 'white')
    toolbar = Image.fromarray(tracker.template).convert('RGB')
    scene.paste(toolbar, (100, 80))
    scene.paste(toolbar, (950, 80))
    with pytest.raises(TrackingError, match='More than one'):
        tracker.locate(scene)


def test_normalized_reading_region_and_click_share_one_transform():
    view = ViewTransform(.5, 10, 30)
    raw = Image.new('RGB', (1008, 711), 'white')
    from PIL import ImageDraw
    draw = ImageDraw.Draw(raw)
    point = view.point(924, 570)
    draw.rectangle((point[0]-5, point[1]-5, point[0]+5, point[1]+5), fill='red')
    normalized = view.normalize(raw, (1907, 1032))
    assert normalized.getpixel((924, 570)) == (255, 0, 0)
