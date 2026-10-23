from queue import Queue
from types import SimpleNamespace
from royalty_entry.gui import App

def test_identity_check_reads_two_fresh_frames_without_running_payments(monkeypatch):
    from royalty_entry import desktop, identity_ocr, engine
    frames=[]
    class Driver:
        def __init__(self,*args):self.ocr=None
        def expect(self,stage):
            assert stage=='general'
            frames.append(object())
            return frames[-1]
        def crop(self,image,key):return key
        def wait(self,*args):pass
    monkeypatch.setattr(desktop,'RemoteDriver',Driver)
    monkeypatch.setattr(identity_ocr,'read_identity',lambda o,image,kind: '1265484726' if kind=='license' else 'PUB485')
    def forbidden(*a,**kw):raise AssertionError('Read-only identity test must not run payments')
    monkeypatch.setattr(engine,'run',forbidden)
    app=SimpleNamespace(messages=Queue(),stop=None)
    App.worker(app,(),{},'identity')
    kind,result=app.messages.get_nowait()
    assert kind=='done' and 'PUB485' in result and '1265484726' in result
    assert len(frames)==2 and frames[0] is not frames[1]
