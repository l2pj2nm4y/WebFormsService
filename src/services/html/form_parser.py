"""HTML form parser for extracting form field definitions.

Parses HTML content to extract form fields, their types, attributes, and structure
for prompt generation.
"""

from dataclasses import dataclass
from html.parser import HTMLParser

from src.lib.logging import get_logger

logger = get_logger(__name__)


@dataclass
class FormField:
    """Represents a form field extracted from HTML."""

    name: str
    field_type: str  # input type, select, textarea, etc.
    label: str | None = None
    required: bool = False
    placeholder: str | None = None
    options: list[str] | None = None  # For select/radio/checkbox
    pattern: str | None = None  # Validation pattern
    min_value: str | None = None
    max_value: str | None = None
    min_length: int | None = None
    max_length: int | None = None
    multiple: bool = False  # For file inputs or multi-select
    accept: str | None = None  # For file inputs


class FormParser(HTMLParser):
    """HTML parser that extracts form fields and their metadata."""

    def __init__(self) -> None:
        """Initialize form parser."""
        super().__init__()
        self.fields: list[FormField] = []
        self.current_label: str | None = None
        self.current_select: dict | None = None
        self.current_fieldset: str | None = None
        self.in_label = False
        self.label_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Handle opening tags."""
        attrs_dict = dict(attrs)

        if tag == "label":
            self.in_label = True
            self.label_text = []
            # Check if label has a "for" attribute
            self.current_label = attrs_dict.get("for")

        elif tag == "fieldset":
            # Track fieldset legend for grouping
            pass

        elif tag == "input":
            self._parse_input_field(attrs_dict)

        elif tag == "select":
            self.current_select = {
                "name": attrs_dict.get("name"),
                "required": "required" in attrs_dict,
                "multiple": "multiple" in attrs_dict,
                "options": [],
            }

        elif tag == "option" and self.current_select is not None:
            value = attrs_dict.get("value")
            if value:
                self.current_select["options"].append(value)

        elif tag == "textarea":
            self._parse_textarea_field(attrs_dict)

    def handle_endtag(self, tag: str) -> None:
        """Handle closing tags."""
        if tag == "label":
            self.in_label = False
            if self.label_text:
                self.current_label = " ".join(self.label_text).strip()

        elif tag == "select" and self.current_select is not None:
            # Create field from select element
            name = self.current_select["name"]
            if name:
                field = FormField(
                    name=name,
                    field_type="select",
                    label=self.current_label,
                    required=self.current_select["required"],
                    multiple=self.current_select["multiple"],
                    options=self.current_select["options"],
                )
                self.fields.append(field)
                logger.debug(
                    "parsed_select_field",
                    name=name,
                    options_count=len(field.options or []),
                )
            self.current_select = None
            self.current_label = None

    def handle_data(self, data: str) -> None:
        """Handle text data inside tags."""
        if self.in_label:
            self.label_text.append(data.strip())

    def _parse_input_field(self, attrs: dict[str, str | None]) -> None:
        """Parse an input field and add to fields list."""
        name = attrs.get("name")
        if not name:
            return  # Skip unnamed inputs

        field_type = attrs.get("type", "text")

        # Skip hidden and submit/button inputs
        if field_type in ("hidden", "submit", "button", "reset", "image"):
            return

        field = FormField(
            name=name,
            field_type=field_type,
            label=self.current_label or attrs.get("aria-label"),
            required="required" in attrs,
            placeholder=attrs.get("placeholder"),
            pattern=attrs.get("pattern"),
            min_value=attrs.get("min"),
            max_value=attrs.get("max"),
            min_length=int(attrs["minlength"]) if attrs.get("minlength") else None,
            max_length=int(attrs["maxlength"]) if attrs.get("maxlength") else None,
            multiple="multiple" in attrs,
            accept=attrs.get("accept"),
        )

        self.fields.append(field)
        logger.debug("parsed_input_field", name=name, type=field_type)

        # Reset label for next field
        if not self.in_label:
            self.current_label = None

    def _parse_textarea_field(self, attrs: dict[str, str | None]) -> None:
        """Parse a textarea field and add to fields list."""
        name = attrs.get("name")
        if not name:
            return

        field = FormField(
            name=name,
            field_type="textarea",
            label=self.current_label or attrs.get("aria-label"),
            required="required" in attrs,
            placeholder=attrs.get("placeholder"),
            min_length=int(attrs["minlength"]) if attrs.get("minlength") else None,
            max_length=int(attrs["maxlength"]) if attrs.get("maxlength") else None,
        )

        self.fields.append(field)
        logger.debug("parsed_textarea_field", name=name)

        # Reset label for next field
        if not self.in_label:
            self.current_label = None

    def parse_html(self, html_content: str) -> list[FormField]:
        """Parse HTML content and extract form fields.

        Args:
            html_content: HTML string to parse

        Returns:
            list[FormField]: List of extracted form fields
        """
        self.fields = []
        self.current_label = None
        self.current_select = None
        self.in_label = False
        self.label_text = []

        try:
            self.feed(html_content)
            logger.info("html_parsing_complete", field_count=len(self.fields))
            return self.fields
        except Exception as e:
            logger.error("html_parsing_failed", error=str(e), exc_info=True)
            raise


# Global instance
_form_parser: FormParser | None = None


def get_form_parser() -> FormParser:
    """Get or create global form parser instance.

    Returns:
        FormParser: Configured form parser
    """
    global _form_parser

    if _form_parser is None:
        _form_parser = FormParser()

    return _form_parser
