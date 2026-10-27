"""PDF drawing evidence and raster preview, without inventing model geometry."""
from io import BytesIO
from contextlib import contextmanager, closing
from threading import RLock
from calculations.validation import finite

PDF_LOCK = RLock()  # PDFium calls must not run concurrently across Streamlit sessions.


@contextmanager
def _open(data):
    try:
        import pypdfium2 as pdfium
    except ImportError as error:
        raise ValueError('PDF parser unavailable. Install requirements-models.txt and restart the app.') from error
    with PDF_LOCK:
        try:
            document = pdfium.PdfDocument(data)
        except pdfium.PdfiumError as error:
            raise ValueError('Unable to open PDF. Check that it is valid and not password-protected.') from error
        try:
            yield document
        except pdfium.PdfiumError as error:
            raise ValueError('Unable to read this PDF page or text stream.') from error
        finally:
            document.close()


def read_pdf(data):
    if not data.lstrip().startswith(b'%PDF-'):
        raise ValueError('PDF header is missing; supply an actual PDF drawing.')
    objects = []
    with _open(data) as document:
        if not 1 <= len(document) <= 50:
            raise ValueError('PDF intake supports 1–50 pages. Split larger drawing sets before upload.')
        remaining = 500000
        for index in range(len(document)):
            with closing(document[index]) as page:
                width, height = page.get_size()
                finite('PDF page width', width, positive=True); finite('PDF page height', height, positive=True)
                with closing(page.get_textpage()) as textpage:
                    count = textpage.count_chars()
                    take = min(count, 100000, remaining)
                    text = textpage.get_text_range(0, take) if take else ''
                    remaining -= take
                objects.append(dict(source_id=f'PDF-PAGE-{index+1}', source_class='PDFPage',
                    kind='drawing_page', name=f'Page {index+1}', system='', page_index=index,
                    page_width_pt=width, page_height_pt=height, text=text, text_truncated=take < count,
                    text_status='EXTRACTED' if text.strip() else 'NO_TEXT_OR_SCAN',
                    length_m=None, nominal_mm=None, geometry_status='NOT_EVALUATED'))
    return dict(format='PDF', schema='PDF drawing', model_id=None, geometry_ready=False,
        intake_status='DRAWING_REVIEW_ONLY', objects=objects, connections=[],
        unit_evidence=dict(length_scale_to_m=None, source='Page dimensions are PDF points; drawing scale is unconfirmed'),
        limitations=['PDF pages and text are drawing evidence, not connected plumbing model geometry.',
            'Printed scale, labels and dimensions are not automatically accepted as measured pipe data.',
            'Image-only pages need OCR or manual review; this intake does not perform OCR.',
            'No hydraulic, slope, fixture-load or code-compliance pass is inferred from PDF content.'])


def preview_pdf(data, page_index):
    with _open(data) as document:
        if not isinstance(page_index, int) or isinstance(page_index, bool) or not 0 <= page_index < len(document):
            raise ValueError('Unknown PDF page')
        with closing(document[page_index]) as page:
            width, height = page.get_size()
            if width <= 0 or height <= 0:
                raise ValueError('Invalid PDF page dimensions')
            # Bound raster memory regardless of the source page's declared size.
            scale = min(2., 1400 / width, 1400 / height)
            bitmap = page.render(scale=scale)
            try:
                image = bitmap.to_pil()
                out = BytesIO()
                image.save(out, format='PNG')
                return out.getvalue()
            finally:
                bitmap.close()
