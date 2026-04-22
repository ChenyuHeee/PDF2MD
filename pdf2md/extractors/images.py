"""图片抽取（含跨页去重）。

策略：
- 用 page.get_images(full=True) 拿到 xref 列表；
- 用 doc.extract_image(xref) 拿到二进制；
- 以 SHA1(image bytes) 为键全局去重；
- 用 page.get_image_rects(xref) 取该图在本页的位置 bbox（用于阅读顺序）。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict, List, Optional

from ..types import ImageBlock

_MIN_PIXELS = 32 * 32  # 太小的（背景花纹/装饰线）丢掉


class ImageWriter:
    """跨页累积的图片写入器，自动去重。"""

    def __init__(self, asset_dir: Path, rel_prefix: str):
        self.asset_dir = asset_dir
        self.rel_prefix = rel_prefix.rstrip("/")
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        self._hash_to_rel: Dict[str, str] = {}
        self._counter = 0

    def _save(self, data: bytes, ext: str) -> str:
        digest = hashlib.sha1(data).hexdigest()
        if digest in self._hash_to_rel:
            return self._hash_to_rel[digest]
        self._counter += 1
        filename = f"img_{self._counter:04d}.{ext}"
        (self.asset_dir / filename).write_bytes(data)
        rel = f"{self.rel_prefix}/{filename}" if self.rel_prefix else filename
        self._hash_to_rel[digest] = rel
        return rel

    def extract_page(self, doc, page) -> List[ImageBlock]:
        out: List[ImageBlock] = []
        for info in page.get_images(full=True):
            xref = info[0]
            try:
                pix = doc.extract_image(xref)
            except Exception:
                continue
            data: Optional[bytes] = pix.get("image")
            if not data:
                continue
            w = pix.get("width", 0)
            h = pix.get("height", 0)
            if w * h < _MIN_PIXELS:
                continue
            ext = pix.get("ext", "png")

            try:
                rects = page.get_image_rects(xref)
            except Exception:
                rects = []
            if not rects:
                # 给一个伪 bbox：放页底
                bbox = (0.0, page.rect.height - 1, page.rect.width, page.rect.height)
            else:
                r = rects[0]
                bbox = (r.x0, r.y0, r.x1, r.y1)

            rel = self._save(data, ext)
            out.append(ImageBlock(bbox=bbox, rel_path=rel))
        return out
