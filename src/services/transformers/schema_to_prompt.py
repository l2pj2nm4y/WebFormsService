"""Transform FormSchema to PromptFile for AI data extraction.

Converts AI-generated FormSchema (with sections, fields, constraints) into
PromptFile format with hierarchical sections and bracketed notation for fields.
"""

from src.lib.logging import get_logger
from src.models.prompt import FormInfo, PromptFile, PromptSection
from src.models.schema import FormField, FormSchema, FormSection

logger = get_logger(__name__)


def _field_to_bracket_notation(field: FormField) -> str:
    """Convert FormField to bracketed notation string.

    Args:
        field: FormField to convert

    Returns:
        str: Bracketed notation string like "[Required: string - Description, Constraints]"
    """
    # Determine if required or optional
    req_opt = "Required" if field.required else "Optional"

    # Build the description part
    parts = [field.description]

    # Add constraints if present
    constraints_parts = []
    for constraint in field.constraints:
        if constraint.type == "minLength" and constraint.value:
            constraints_parts.append(f"min {constraint.value} chars")
        elif constraint.type == "maxLength" and constraint.value:
            constraints_parts.append(f"max {constraint.value} chars")
        elif constraint.type == "pattern" and constraint.value:
            constraints_parts.append(f"pattern: {constraint.value}")
        elif constraint.type == "enum" and constraint.value:
            # constraint.value is list of allowed values
            values_str = "|".join(constraint.value)
            constraints_parts.append(f"One of: {values_str}")
        elif constraint.type == "min" and constraint.value is not None:
            constraints_parts.append(f"min: {constraint.value}")
        elif constraint.type == "max" and constraint.value is not None:
            constraints_parts.append(f"max: {constraint.value}")

    # Build final description with constraints
    description = field.description
    if constraints_parts:
        description = f"{field.description}, {', '.join(constraints_parts)}"

    # Format: [Required/Optional: type - description]
    return f"[{req_opt}: {field.type} - {description}]"


def _process_section(
    section: FormSection, parent_path: str = ""
) -> PromptSection:
    """Convert FormSection to PromptSection recursively.

    Args:
        section: FormSection to convert
        parent_path: Parent path for building dot-notation paths

    Returns:
        PromptSection: Converted section with fields and subsections
    """
    # Build section path
    section_path = f"{parent_path}.{section.name}" if parent_path else section.name

    # Convert fields to bracketed notation
    fields_dict = {}
    for field in section.fields:
        fields_dict[field.name] = _field_to_bracket_notation(field)

    # Recursively process subsections
    subsections = []
    for subsection in section.subsections:
        subsections.append(_process_section(subsection, section_path))

    # Extract visibility condition from section
    visible_when = None
    if section.visibility_rules:
        # Convert first visibility rule to simple condition string
        # Format: "field == 'value'" or "field != 'value'"
        rule = section.visibility_rules[0]  # Use first rule for now
        operator = rule.operator
        field = rule.field
        value = rule.value

        if operator == "equals":
            visible_when = f'{field} == "{value}"'
        elif operator == "notEquals":
            visible_when = f'{field} != "{value}"'
        elif operator == "contains":
            visible_when = f'{field} contains "{value}"'
        else:
            # For other operators, use a generic format
            visible_when = f'{field} {operator} "{value}"'

    return PromptSection(
        name=section.name,
        description=section.description,
        path=section_path,
        fields=fields_dict,
        subsections=subsections,
        visible_when=visible_when,
    )


def formschema_to_promptfile(schema: FormSchema) -> PromptFile:
    """Convert FormSchema to PromptFile with enhanced structure.

    Transforms AI-generated FormSchema into PromptFile format suitable for
    AI data extraction. Preserves:
    - Section hierarchy and descriptions
    - Field specifications in bracketed notation
    - Array/table configurations
    - Visibility conditions
    - Page context from PageIdentification

    Args:
        schema: FormSchema to convert

    Returns:
        PromptFile: Converted prompt file with hierarchical sections

    Raises:
        ValueError: If schema is invalid or conversion fails
    """
    logger.info(
        "schema_to_prompt_conversion_start",
        form_name=schema.form_name,
        section_count=len(schema.sections),
    )

    try:
        # Build FormInfo from schema and page identification
        form_info = FormInfo(
            form_name=schema.form_name,
            description=schema.description,
            page_identifier=schema.page_identifier,
            url=schema.page_identification.url,
            page_headings=schema.page_identification.page_headings,
            form_headings=schema.page_identification.form_headings,
            visual_sections=schema.page_identification.visual_sections,
            navigation_buttons=schema.page_identification.navigation_buttons,
            progress_indicator=schema.page_identification.progress_indicator,
            page_number=schema.page_identification.page_number,
        )

        # Convert all sections recursively
        prompt_sections = []
        for section in schema.sections:
            prompt_section = _process_section(section)
            prompt_sections.append(prompt_section)

        # Create PromptFile
        prompt_file = PromptFile(
            schema_version="1.0",
            form_info=form_info,
            sections=prompt_sections,
            metadata={
                "generatedFrom": "schema",
                "originalFormName": schema.form_name,
                "originalPageIdentifier": schema.page_identifier,
            },
        )

        logger.info(
            "schema_to_prompt_conversion_complete",
            form_name=schema.form_name,
            section_count=len(prompt_sections),
            total_sections_with_subsections=len(prompt_file.get_all_sections()),
            required_fields_count=len(prompt_file.get_required_fields()),
        )

        return prompt_file

    except Exception as e:
        logger.error(
            "schema_to_prompt_conversion_failed",
            form_name=schema.form_name,
            error=str(e),
            exc_info=True,
        )
        raise
