from io import BytesIO
from typing import Optional, Dict, Any
import base64

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
    from reportlab.lib.utils import ImageReader
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False
    RLImage = None  # type: ignore
    ImageReader = None  # type: ignore

try:
    from PIL import Image as PILImage
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False


def _fetch_image_bytes(image_url: str) -> Optional[bytes]:
    try:
        import requests
        r = requests.get(image_url, timeout=5)
        if r.ok and r.content:
            return r.content
    except Exception:
        return None
    return None


def _decode_base64_image(b64: str) -> Optional[bytes]:
    try:
        # Accept raw base64 or data URL
        if b64.startswith("data:image"):
            header, data = b64.split(",", 1)
            return base64.b64decode(data)
        return base64.b64decode(b64)
    except Exception:
        return None


def _prepare_rl_image(img_bytes: bytes, max_width: float) -> Optional[Any]:
    if not REPORTLAB_AVAILABLE or RLImage is None:
        return None
    try:
        if PIL_AVAILABLE:
            im = PILImage.open(BytesIO(img_bytes))
            # Convert to RGB if needed for ReportLab
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGB")
            w, h = im.size
            scale = min(1.0, max_width / float(w))
            new_w, new_h = int(w * scale), int(h * scale)
            buf = BytesIO()
            im.resize((new_w, new_h), PILImage.LANCZOS).save(buf, format="PNG")
            buf.seek(0)
            return RLImage(buf, width=new_w, height=new_h)
        # Fallback without PIL: let ReportLab scale using width only
        if ImageReader is None:
            return None
        return RLImage(ImageReader(BytesIO(img_bytes)), width=max_width)
    except Exception:
        return None


def generate_pdf_bytes(analysis: Dict[str, Any], image_url: Optional[str] = None, image_base64: Optional[str] = None) -> Optional[bytes]:
    """
    Generate a PDF report from an analysis dict. Returns bytes or None if reportlab unavailable.
    Embeds image by default when available (base64 preferred, else url).
    """
    if not REPORTLAB_AVAILABLE:
        return None

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    # Title
    story.append(Paragraph("AdAware AI - Analysis Report", styles['Title']))
    story.append(Spacer(1, 12))

    # --- Image embedding (default) ---
    # Source precedence: explicit arg -> analysis fields
    src_b64 = image_base64 or analysis.get("image_base64")
    src_url = image_url or analysis.get("image_url")
    img_bytes: Optional[bytes] = None
    if src_b64:
        img_bytes = _decode_base64_image(src_b64)
    if not img_bytes and src_url:
        img_bytes = _fetch_image_bytes(src_url)

    if img_bytes:
        # Compute usable max width (A4 minus margins)
        usable_width = doc.pagesize[0] - doc.leftMargin - doc.rightMargin
        rl_img = _prepare_rl_image(img_bytes, max_width=usable_width)
        if rl_img:
            story.append(Paragraph("Analyzed image", styles['Heading3']))
            story.append(rl_img)
            story.append(Spacer(1, 12))

    # Summary fields (defensive reads)
    brand = analysis.get("brand") or analysis.get("product_info", {}).get("brand_name") or "Unknown"
    product = analysis.get("product") or analysis.get("product_info", {}).get("product_name") or "Unknown"
    category = analysis.get("category") or analysis.get("product_info", {}).get("category") or "Unclassified"
    trust = analysis.get("trust_score", analysis.get("legitimacy_score"))
    if isinstance(trust, float):
        trust_disp = f"{int(round(trust * 100))}/100"
    else:
        trust_disp = str(trust or "N/A")
    confidence = analysis.get("model_confidence", analysis.get("confidence"))
    similarity = analysis.get("image_text_similarity", None)

    # Summary table
    summary_data = [
        ["Brand", str(brand)],
        ["Product", str(product)],
        ["Category", str(category)],
        ["Trust score", trust_disp],
        ["Model confidence", f"{confidence:.2f}" if isinstance(confidence, (int, float)) else str(confidence or "N/A")],
        ["Image-text similarity", "Unavailable" if similarity is None else f"{similarity:.2f}"],
    ]
    table = Table(summary_data, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.grey),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
    ]))
    story.append(table)
    story.append(Spacer(1, 16))

    # Price
    price = analysis.get("product_info", {}).get("formatted_price") or analysis.get("price") or "Price not detected"
    story.append(Paragraph(f"Price: {price}", styles['Normal']))
    story.append(Spacer(1, 12))

    # Flags / advisories
    flags = analysis.get("flags") or []
    advisories = analysis.get("health_advisory") or analysis.get("advisories") or []
    if flags:
        story.append(Paragraph("Flags:", styles['Heading3']))
        for f in flags:
            story.append(Paragraph(f"- {f}", styles['Normal']))
        story.append(Spacer(1, 8))
    if advisories:
        story.append(Paragraph("Health Advisory:", styles['Heading3']))
        if isinstance(advisories, list):
            for a in advisories:
                story.append(Paragraph(f"- {a}", styles['Normal']))
        else:
            story.append(Paragraph(f"{advisories}", styles['Normal']))
        story.append(Spacer(1, 8))

    # OCR text
    ocr_text = analysis.get("text") or analysis.get("ocr_text") or ""
    if ocr_text:
        story.append(Paragraph("Extracted Text:", styles['Heading3']))
        story.append(Paragraph(ocr_text.replace("\n", "<br/>"), styles['Normal']))
        story.append(Spacer(1, 12))

    # Evidence / rules
    evidence = analysis.get("evidence_spans") or []
    if evidence:
        story.append(Paragraph("Evidence:", styles['Heading3']))
        for e in evidence:
            txt = e.get("text") or ""
            subcat = e.get("subcategory") or "other"
            story.append(Paragraph(f"[{subcat}] {txt}", styles['Normal']))
        story.append(Spacer(1, 12))

    doc.build(story)
    buf.seek(0)
    return buf.read()
