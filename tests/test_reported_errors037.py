import cv2
import numpy as np
import pytest
from PIL import Image
from royalty_entry.tracking import ToolbarTracker,TrackingError

@pytest.mark.parametrize('noise',[20,25])
def test_partial_toolbar_with_matching_shading_is_not_a_second_manager(noise):
    tracker=ToolbarTracker();template=tracker.template
    h,w=template.shape
    gradient=np.repeat(np.median(template,axis=1).astype('uint8')[:,None],w,axis=1)
    partial=template.copy();partial[:,2*w//3:]=gradient[:,2*w//3:]
    rng=np.random.default_rng(37)
    primary=np.clip(template.astype(float)+rng.normal(0,noise,template.shape),0,255).astype('uint8')
    # Their raw correlations differ by < .04: the old tracker rejected this.
    score=cv2.matchTemplate(primary,template,cv2.TM_CCOEFF_NORMED)[0,0]
    runner=cv2.matchTemplate(partial,template,cv2.TM_CCOEFF_NORMED)[0,0]
    assert 0 < score-runner < .04
    scene=np.full((500,1600),235,dtype=np.uint8)
    scene[100:100+h,100:100+w]=primary
    scene[100:100+h,950:950+w]=partial
    view=tracker.locate(Image.fromarray(scene).convert('RGB'))
    assert view.point(*tracker.reference)==(100,100)

@pytest.mark.parametrize('noise',[0,20])
def test_two_complete_toolbars_are_still_rejected(noise):
    tracker=ToolbarTracker();template=tracker.template;h,w=template.shape
    rng=np.random.default_rng(37)
    primary=np.clip(template.astype(float)+rng.normal(0,noise,template.shape),0,255).astype('uint8')
    scene=np.full((500,1600),235,dtype=np.uint8)
    scene[100:100+h,100:100+w]=primary
    scene[100:100+h,950:950+w]=template
    with pytest.raises(TrackingError,match='More than one'):
        tracker.locate(Image.fromarray(scene).convert('RGB'))
