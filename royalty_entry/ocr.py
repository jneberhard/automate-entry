"""Windows' local OCR. No screenshots or workbook values leave this computer."""
import asyncio
import io
from dataclasses import dataclass


@dataclass(frozen=True)
class Line:
    text: str
    x: float
    y: float
    width: float
    height: float


class WindowsOCR:
    def __init__(self):
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine
        self.engine = OcrEngine.try_create_from_language(Language('en-US'))
        if self.engine is None:
            raise RuntimeError('Windows English OCR is unavailable. Install the English language OCR feature in Windows Settings.')

    async def _read(self, image):
        from winrt.windows.graphics.imaging import BitmapDecoder
        from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream
        payload = io.BytesIO()
        image.convert('RGB').save(payload, format='PNG')
        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream)
        writer.write_bytes(payload.getvalue())
        await writer.store_async()
        writer.detach_stream()
        stream.seek(0)
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        result = await self.engine.recognize_async(bitmap)
        lines = []
        for line in result.lines:
            words = list(line.words)
            if not words:
                continue
            left = min(w.bounding_rect.x for w in words)
            top = min(w.bounding_rect.y for w in words)
            right = max(w.bounding_rect.x + w.bounding_rect.width for w in words)
            bottom = max(w.bounding_rect.y + w.bounding_rect.height for w in words)
            lines.append(Line(line.text, left, top, right-left, bottom-top))
        bitmap.close()
        stream.close()
        return lines

    def lines(self, image, scale=3):
        from PIL import Image
        from winrt.windows.media.ocr import OcrEngine
        scale = min(scale, OcrEngine.max_image_dimension/max(image.size))
        enlarged = image.resize((max(1, round(image.width*scale)), max(1, round(image.height*scale))), Image.Resampling.LANCZOS)
        return [Line(l.text, l.x/scale, l.y/scale, l.width/scale, l.height/scale)
                for l in asyncio.run(asyncio.wait_for(self._read(enlarged), timeout=15))]

    def text(self, image):
        return ' '.join(line.text for line in self.lines(image))
