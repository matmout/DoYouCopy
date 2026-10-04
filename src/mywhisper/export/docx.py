"""Word document without any dependency: a .docx is a zip of a few XML parts."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Sequence
from xml.sax.saxutils import escape

from mywhisper.core.types import Segment
from mywhisper.export.base import register

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

DOCUMENT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>{paragraphs}<w:sectPr/></w:body>
</w:document>"""

PARAGRAPH = '<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'


class DocxExporter:
    suffix = ".docx"
    label = "Document Word"

    def render(self, segments: Sequence[Segment], **_options) -> bytes:
        paragraphs = "".join(PARAGRAPH.format(text=escape(s.text)) for s in segments if s.text)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", CONTENT_TYPES)
            archive.writestr("_rels/.rels", RELS)
            archive.writestr("word/document.xml", DOCUMENT.format(paragraphs=paragraphs))
        return buffer.getvalue()


register(DocxExporter())
