
from typing import Optional
from pydantic import BaseModel

class HoverPayload(BaseModel):
    image_base64: Optional[str] = None
    image_url: Optional[str] = None
    caption_text: Optional[str] = None
    page_origin: Optional[str] = None
    consent: Optional[bool] = False
