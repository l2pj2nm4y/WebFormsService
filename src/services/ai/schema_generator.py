"""AI-powered form schema generation from screenshots.

Generates comprehensive JSON schema representing form fields, sections,
and validation rules using vision-capable AI models via LiteLLM with OpenRouter.

Uses LangFuse for observability and tracing.
"""

import base64
import json
import os
import time
from typing import Any

import litellm
from litellm import acompletion

from src.lib.config import get_config
from src.lib.image_utils import resize_image_for_vision_api
from src.lib.logging import get_logger, log_ai_operation
from src.models.schema import FormSchema

logger = get_logger(__name__)

# Initialize LangFuse callbacks for LiteLLM
_langfuse_initialized = False


def _initialize_langfuse() -> None:
    """Initialize LangFuse callbacks for LiteLLM tracing."""
    global _langfuse_initialized
    if _langfuse_initialized:
        return

    config = get_config()
    if config.langfuse.enabled and config.langfuse.public_key:
        litellm.success_callback = ["langfuse"]
        litellm.failure_callback = ["langfuse"]
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", config.langfuse.public_key)
        os.environ.setdefault("LANGFUSE_SECRET_KEY", config.langfuse.secret_key)
        os.environ.setdefault("LANGFUSE_HOST", config.langfuse.host)
        logger.info("langfuse_tracing_enabled", host=config.langfuse.host)

    _langfuse_initialized = True


# System prompt for schema generation - comprehensive form analysis
SCHEMA_GENERATION_SYSTEM_PROMPT = """<role>
You are an expert at analysing screenshots and constructing JSON.
</role>

<objective>
Analyse the form screenshot provided in the user prompt and generate a comprehensive JSON data structure representing all required input fields in a normalized, Pydantic-compatible format.
</objective>

<output_structure_specification>
    <page_identification_guidance>
        CRITICAL: Extract EXACT text as it appears on the page - character-for-character accuracy is essential.
        This data is used to match schemas from the same page across multiple screenshots.

        Fields to populate with EXACT text from screenshot:
        - "page_headings": Main page-level headings or titles (exactly as shown)
        - "form_headings": Form section headings and subsection titles (exactly as shown, preserve order)
        - "visual_sections": Visual layout sections (header, left_navigation_panel, main_content_form, right_sidebar, footer, etc.)
        - "navigation_buttons": Navigation button labels (exactly as shown)
        - "progress_indicator": Progress indicator if visible (e.g., '15%', 'Step 2 of 5')
        - "page_number": Page number if visible (e.g., '3/20', 'Page 3 of 20')

        Systematically analyze the screenshot:
        - What are the most prominent headings or titles you can see?
        - How is the page visually organized (sections/layout)?
        - Is there any progress indication or page number?
        - Are there any page navigation buttons?
    </page_identification_guidance>

    <field_types>
        <type>string - Text input field</type>
        <type>number - Numeric input field</type>
        <type>boolean - Checkbox or toggle field</type>
        <type>date - Date picker (YYYY-MM-DD)</type>
        <type>datetime - Date and time picker (ISO 8601)</type>
        <type>time - Time picker (HH:MM:SS)</type>
        <type>email - Email input field</type>
        <type>phone - Phone number input field</type>
        <type>url - URL input field</type>
        <type>file - File upload field</type>
        <type>currency - Monetary amount field</type>
        <type>percentage - Percentage value field</type>
        <type>array - Multiple values field (checkboxes group, multi-select)</type>
        <type>object - Nested structure for complex fields</type>
    </field_types>

    <constraint_types>
        <constraint name="maxLength" description="Maximum character length for text fields"/>
        <constraint name="minLength" description="Minimum character length for text fields"/>
        <constraint name="pattern" description="Regex pattern for validation"/>
        <constraint name="enum" description="List of allowed values (for dropdowns/radios)"/>
        <constraint name="min" description="Minimum numeric value"/>
        <constraint name="max" description="Maximum numeric value"/>
        <constraint name="allowedFormats" description="Allowed file formats (PDF, DOC, etc.)"/>
        <constraint name="maxFileSize" description="Maximum file size in MB"/>
        <constraint name="required" description="Field must have a value"/>
        <constraint name="dateRange" description="Valid date range"/>
        <constraint name="unique" description="Value must be unique"/>
    </constraint_types>
</output_structure_specification>

<field_description_requirements>
    <purpose>Field descriptions must explain WHAT information the user needs to provide, not just restate the label</purpose>

    <description_patterns>
        <pattern>
            <field_type>Name fields</field_type>
            <bad_description>User's first name</bad_description>
            <good_description>Enter your legal first name as it appears on official documents</good_description>
        </pattern>
        <pattern>
            <field_type>Date fields</field_type>
            <bad_description>Date of birth</bad_description>
            <good_description>Select your date of birth in DD/MM/YYYY format - must be 18 years or older</good_description>
        </pattern>
        <pattern>
            <field_type>Selection fields</field_type>
            <bad_description>Country selection</bad_description>
            <good_description>Choose the country where you currently hold citizenship</good_description>
        </pattern>
        <pattern>
            <field_type>Boolean fields</field_type>
            <bad_description>Accept terms</bad_description>
            <good_description>Check this box to confirm you have read and agree to the terms and conditions</good_description>
        </pattern>
        <pattern>
            <field_type>File upload fields</field_type>
            <bad_description>Upload document</bad_description>
            <good_description>Upload a scanned copy or photo of your passport bio page (PDF or JPG, max 5MB)</good_description>
        </pattern>
        <pattern>
            <field_type>Array/Multiple selection</field_type>
            <bad_description>Select interests</bad_description>
            <good_description>Choose up to 5 topics that interest you - this helps us customize your experience</good_description>
        </pattern>
    </description_patterns>

    <description_components>
        <component>Action verb (Enter, Select, Choose, Upload, Provide, Specify)</component>
        <component>What specific information is needed</component>
        <component>Any format requirements or constraints</component>
        <component>Why the information is needed (if apparent from context)</component>
        <component>Any conditions or eligibility requirements</component>
    </description_components>

    <contextual_hints>
        <hint>If field has placeholder text, incorporate that guidance into the description</hint>
        <hint>If field has help text or tooltip, include that information</hint>
        <hint>If field has validation rules visible, mention them in the description</hint>
        <hint>If field is conditional on another field, explain the condition</hint>
        <hint>If field has a specific format (phone, SSN, etc.), specify the format</hint>
    </contextual_hints>
</field_description_requirements>

<section_description_requirements>
    <purpose>Section descriptions must explain the PURPOSE of the information group and how it will be used</purpose>

    <description_patterns>
        <pattern>
            <section_type>Personal Information</section_type>
            <bad_description>User personal information section</bad_description>
            <good_description>Basic personal details required to verify your identity and create your account</good_description>
        </pattern>
        <pattern>
            <section_type>Contact Details</section_type>
            <bad_description>Contact information fields</bad_description>
            <good_description>Contact information used for account verification and important notifications</good_description>
        </pattern>
        <pattern>
            <section_type>Documents</section_type>
            <bad_description>Document upload section</bad_description>
            <good_description>Supporting documents required to verify your eligibility and process your application</good_description>
        </pattern>
        <pattern>
            <section_type>Preferences</section_type>
            <bad_description>User preferences</bad_description>
            <good_description>Communication and service preferences to customize your experience</good_description>
        </pattern>
    </description_patterns>

    <description_components>
        <component>Purpose of collecting this group of information</component>
        <component>How the information will be used</component>
        <component>Any eligibility or requirements for the section</component>
        <component>Whether the section is conditional on previous answers</component>
    </description_components>
</section_description_requirements>

<table_field_handling>
    <detection_rules>
        <rule>Identify table/grid inputs by these visual cues:
            - Column headers visible
            - "Add row" or "Add details" button
            - Multiple rows of similar fields
            - Delete/remove icons per row
            - Grid-like layout with consistent columns
        </rule>
    </detection_rules>

    <table_structure_extraction>
        <instruction>For table/grid inputs, extract the complete structure:</instruction>
        <steps>
            <step>Identify this is a table input by setting input_format: "table"</step>
            <step>Set type: "array" as the base type</step>
            <step>Extract column definitions from headers or first row</step>
            <step>Create table_config with column specifications</step>
            <step>Set array_config.item_type: "object" for structured rows</step>
        </steps>
    </table_structure_extraction>

    <table_config_structure>
        {
            "input_format": "table",
            "table_config": {
                "add_button_text": "Add row" or "Add details",
                "can_delete_rows": boolean,
                "can_reorder_rows": boolean,
                "columns": [
                    {
                        "name": "fieldName",
                        "label": "Column Header Text",
                        "type": "string|number|date|etc",
                        "required": boolean,
                        "width": "percentage or pixels",
                        "editable": boolean,
                        "description": "What the user needs to enter in this column",
                        "constraints": []
                    }
                ],
                "row_validation": {
                    "unique_fields": ["field_that_must_be_unique"],
                    "required_fields": ["fields_required_per_row"]
                }
            },
            "array_config": {
                "item_type": "object",
                "item_schema": {
                    "field1": {
                        "type": "string",
                        "required": true,
                        "description": "Description from column"
                    },
                    "field2": {
                        "type": "date",
                        "required": false,
                        "description": "Description from column"
                    }
                },
                "min_items": 0,
                "max_items": null,
                "allow_empty": true,
                "unique_field": "field_that_identifies_unique_rows"
            }
        }
    </table_config_structure>
</table_field_handling>

<field_analysis_rules>
    <rule priority="1">
        <description>Identify form element type</description>
        <mapping>
            <form_element>Text input, textarea</form_element>
            <field_type>string</field_type>
        </mapping>
        <mapping>
            <form_element>Number input, range slider</form_element>
            <field_type>number</field_type>
        </mapping>
        <mapping>
            <form_element>Single checkbox, toggle switch</form_element>
            <field_type>boolean</field_type>
        </mapping>
        <mapping>
            <form_element>Date picker</form_element>
            <field_type>date</field_type>
        </mapping>
        <mapping>
            <form_element>DateTime picker</form_element>
            <field_type>datetime</field_type>
        </mapping>
        <mapping>
            <form_element>Time picker</form_element>
            <field_type>time</field_type>
        </mapping>
        <mapping>
            <form_element>Email input</form_element>
            <field_type>email</field_type>
        </mapping>
        <mapping>
            <form_element>Phone input</form_element>
            <field_type>phone</field_type>
        </mapping>
        <mapping>
            <form_element>URL input</form_element>
            <field_type>url</field_type>
        </mapping>
        <mapping>
            <form_element>File upload, document upload</form_element>
            <field_type>file</field_type>
        </mapping>
        <mapping>
            <form_element>Currency input</form_element>
            <field_type>currency</field_type>
        </mapping>
        <mapping>
            <form_element>Percentage input</form_element>
            <field_type>percentage</field_type>
        </mapping>
        <mapping>
            <form_element>Multiple checkboxes, multi-select</form_element>
            <field_type>array</field_type>
        </mapping>
        <mapping>
            <form_element>Dropdown/select with single selection</form_element>
            <field_type>string</field_type>
            <note>Add enum constraint with options</note>
        </mapping>
        <mapping>
            <form_element>Radio button group</form_element>
            <field_type>string</field_type>
            <note>Add enum constraint with options</note>
        </mapping>
    </rule>

    <rule priority="1.5">
        <description>Detect and handle table/grid inputs</description>
        <detection>
            <indicator>Column headers present above input area</indicator>
            <indicator>"Add row", "Add details", "Add another" buttons</indicator>
            <indicator>Row delete icons or remove buttons</indicator>
            <indicator>Repeating row structure with consistent fields</indicator>
        </detection>
        <extraction>
            <extract>Column names from headers</extract>
            <extract>Column types from input fields in first row</extract>
            <extract>Required indicators per column</extract>
            <extract>Column widths if visually distinct</extract>
            <extract>Row manipulation capabilities (add/delete/reorder)</extract>
        </extraction>
    </rule>

    <rule priority="2">
        <description>Determine field requirement</description>
        <indicators>
            <required>Asterisk (*), "required" label, validation message</required>
            <optional>No asterisk, "optional" label, placeholder says optional</optional>
        </indicators>
    </rule>

    <rule priority="3">
        <description>Extract constraints from visual cues</description>
        <constraint_extraction>
            <pattern>Maximum X characters → {"type": "maxLength", "value": X}</pattern>
            <pattern>Minimum X characters → {"type": "minLength", "value": X}</pattern>
            <pattern>Between X and Y → [{"type": "min", "value": X}, {"type": "max", "value": Y}]</pattern>
            <pattern>Dropdown/Radio options → {"type": "enum", "value": ["option1", "option2"]} AND populate options field</pattern>
            <pattern>Format hint (e.g., XXX-XX-XXXX) → {"type": "pattern", "value": "regex_pattern"}</pattern>
            <pattern>File types (PDF, DOC) → {"type": "allowedFormats", "value": ["PDF", "DOC"]}</pattern>
            <pattern>Max file size → {"type": "maxFileSize", "value": size_in_mb}</pattern>
        </constraint_extraction>
    </rule>

    <rule priority="4">
        <description>Group related fields into sections</description>
        <grouping_logic>
            <criterion>Visual proximity and borders</criterion>
            <criterion>Semantic relationship (e.g., all address fields)</criterion>
            <criterion>Common heading or label</criterion>
            <criterion>Form fieldsets or sections</criterion>
        </grouping_logic>
    </rule>

    <rule priority="5">
        <description>Identify sensitive fields</description>
        <sensitive_indicators>
            <indicator>Password fields</indicator>
            <indicator>SSN, tax ID, government ID fields</indicator>
            <indicator>Credit card, bank account fields</indicator>
            <indicator>Medical information fields</indicator>
            <indicator>Fields marked as confidential/private</indicator>
        </sensitive_indicators>
    </rule>

    <rule priority="6">
        <description>Configure array fields</description>
        <array_configuration>
            <property>item_type: Type of each array element</property>
            <property>min_items: Minimum required selections</property>
            <property>max_items: Maximum allowed selections</property>
            <property>allow_empty: Whether empty array is valid</property>
            <property>unique_field: Field name for uniqueness check</property>
        </array_configuration>
    </rule>

    <rule priority="7">
        <description>Generate meaningful descriptions for sections and fields</description>
        <section_descriptions>
            <instruction>For each section, explain:</instruction>
            <explain>WHY this information group is being collected</explain>
            <explain>HOW it will be used in the process</explain>
            <explain>WHO needs to complete this section</explain>
            <example>
                Instead of: "Address information"
                Generate: "Residential address where official documents will be mailed - must be current residence"
            </example>
        </section_descriptions>
        <field_descriptions>
            <instruction>For each field, explain:</instruction>
            <explain>WHAT specific answer is required</explain>
            <explain>HOW to format the answer</explain>
            <explain>WHY it's needed (if apparent)</explain>
            <explain>WHEN it applies (if conditional)</explain>
            <example>
                Instead of: "Phone number"
                Generate: "Enter your primary mobile number including country code - used for SMS verification"
            </example>
        </field_descriptions>
    </rule>
</field_analysis_rules>

<analysis_scope>
    <include_only>
        <element>Text input fields (all variants)</element>
        <element>Dropdown/select menus</element>
        <element>Checkboxes (single and groups)</element>
        <element>Radio button groups</element>
        <element>Text areas</element>
        <element>File upload fields</element>
        <element>Date/time pickers</element>
        <element>Number/range inputs</element>
        <element>Multi-select lists</element>
        <element>Toggle switches</element>
        <element>Slider controls</element>
        <element>Table/grid inputs with add/remove row functionality</element>
    </include_only>

    <explicitly_exclude>
        <element>Submit/Cancel/Reset buttons</element>
        <element>Navigation links and tabs</element>
        <element>Static text and labels</element>
        <element>Disabled or readonly fields</element>
        <element>Progress indicators</element>
        <element>Help text and tooltips (extract content but don't create fields)</element>
        <element>Decorative elements</element>
        <element>Headers and footers</element>
    </explicitly_exclude>
</analysis_scope>

<section_organization>
    <principle>Group fields by logical relationship and visual proximity</principle>
    <principle>Create subsections for nested groupings when form has clear hierarchical structure</principle>
    <principle>Each section should represent a cohesive set of related inputs</principle>
    <principle>Section names should be descriptive and match form headings when present</principle>
    <principle>Mark section as required if ALL fields within are required</principle>
    <principle>Every section MUST have a meaningful description explaining its purpose</principle>
    <principle>Every field MUST have a description explaining what answer is needed</principle>
</section_organization>

<example_output>
{
    "page_identifier": "Australian citizenship by descent - Applicant details (3/22)",
    "page_identification": {
        "page_headings": ["Australian Citizenship by Descent Application"],
        "form_headings": ["Applicant Details", "Personal Information", "Travel Documents"],
        "visual_sections": ["header", "navigation_panel", "main_content_form", "footer"],
        "navigation_buttons": ["Previous", "Save and Continue", "Exit Application"],
        "progress_indicator": "15% complete",
        "page_number": "3/22"
    },
    "form_name": "CitizenshipByDescentApplication",
    "description": "Application for Australian citizenship by descent - collecting applicant's personal information and identity verification details",
    "sections": [
        {
            "name": "PersonalInformation",
            "description": "Basic personal details required to verify your identity and create your citizenship certificate",
            "required": true,
            "fields": [
                {
                    "name": "firstName",
                    "type": "string",
                    "required": true,
                    "description": "Enter your legal first name exactly as it appears on your birth certificate or passport",
                    "label": "First Name",
                    "placeholder": "Enter your first name",
                    "default_value": null,
                    "constraints": [
                        {
                            "type": "maxLength",
                            "value": 50,
                            "message": "First name cannot exceed 50 characters"
                        },
                        {
                            "type": "minLength",
                            "value": 1,
                            "message": "First name is required"
                        }
                    ],
                    "options": null,
                    "sensitive": false,
                    "input_format": null,
                    "table_config": null,
                    "array_config": null
                },
                {
                    "name": "gender",
                    "type": "string",
                    "required": true,
                    "description": "Select your gender as recorded on official documents - if this has changed, provide documentation later",
                    "label": "Gender",
                    "placeholder": null,
                    "default_value": null,
                    "constraints": [
                        {
                            "type": "enum",
                            "value": ["Male", "Female", "Non-binary", "Prefer not to say"],
                            "message": "Please select a valid option"
                        }
                    ],
                    "options": ["Male", "Female", "Non-binary", "Prefer not to say"],
                    "sensitive": false,
                    "input_format": null,
                    "table_config": null,
                    "array_config": null
                },
                {
                    "name": "dateOfBirth",
                    "type": "date",
                    "required": true,
                    "description": "Select your date of birth in DD/MM/YYYY format - you must be 18 or older to apply independently",
                    "label": "Date of Birth",
                    "placeholder": "DD/MM/YYYY",
                    "default_value": null,
                    "constraints": [
                        {
                            "type": "dateRange",
                            "value": {
                                "min": "1900-01-01",
                                "max": "2006-01-01"
                            },
                            "message": "Applicant must be at least 18 years old"
                        }
                    ],
                    "options": null,
                    "sensitive": false,
                    "input_format": null,
                    "table_config": null,
                    "array_config": null
                }
            ],
            "subsections": []
        },
        {
            "name": "TravelDocuments",
            "description": "Current and previous travel documents needed to verify identity and track international movement history",
            "required": false,
            "fields": [
                {
                    "name": "otherTravelDocuments",
                    "type": "array",
                    "required": false,
                    "description": "List all other passports and travel documents you hold including expired passports, refugee documents, or ImmiCards",
                    "label": "Other Travel Documents",
                    "placeholder": null,
                    "default_value": [],
                    "constraints": [],
                    "options": null,
                    "sensitive": true,
                    "input_format": "table",
                    "table_config": {
                        "add_button_text": "Add details",
                        "can_delete_rows": true,
                        "can_reorder_rows": false,
                        "columns": [
                            {
                                "name": "documentType",
                                "label": "Document Type",
                                "type": "string",
                                "required": true,
                                "width": "25%",
                                "editable": true,
                                "description": "Select the type of travel document from the list",
                                "constraints": [
                                    {
                                        "type": "enum",
                                        "value": ["Passport", "Titre de Voyage", "PLO56", "DFTTA", "ImmiCard"],
                                        "message": "Select document type"
                                    }
                                ]
                            },
                            {
                                "name": "documentNumber",
                                "label": "Document Number",
                                "type": "string",
                                "required": true,
                                "width": "25%",
                                "editable": true,
                                "description": "Enter the document number exactly as shown on the document",
                                "constraints": [
                                    {
                                        "type": "maxLength",
                                        "value": 50,
                                        "message": "Maximum 50 characters"
                                    }
                                ]
                            },
                            {
                                "name": "issuingCountry",
                                "label": "Issuing Country",
                                "type": "string",
                                "required": true,
                                "width": "25%",
                                "editable": true,
                                "description": "Select the country that issued this travel document",
                                "constraints": []
                            },
                            {
                                "name": "expiryDate",
                                "label": "Expiry Date",
                                "type": "date",
                                "required": false,
                                "width": "25%",
                                "editable": true,
                                "description": "Enter expiry date if shown on document - leave blank for non-expiring documents",
                                "constraints": []
                            }
                        ],
                        "row_validation": {
                            "unique_fields": ["documentNumber"],
                            "required_fields": ["documentType", "documentNumber", "issuingCountry"]
                        }
                    },
                    "array_config": {
                        "item_type": "object",
                        "item_schema": {
                            "documentType": {
                                "type": "string",
                                "required": true,
                                "description": "Type of travel document"
                            },
                            "documentNumber": {
                                "type": "string",
                                "required": true,
                                "description": "Unique document identification number"
                            },
                            "issuingCountry": {
                                "type": "string",
                                "required": true,
                                "description": "Country that issued the document"
                            },
                            "expiryDate": {
                                "type": "date",
                                "required": false,
                                "description": "Document expiration date if applicable"
                            }
                        },
                        "min_items": 0,
                        "max_items": null,
                        "allow_empty": true,
                        "unique_field": "documentNumber"
                    }
                }
            ],
            "subsections": []
        }
    ]
}
</example_output>

<output_rules>
    <format>Raw JSON structure only - no markdown formatting or code blocks</format>
    <validation>Must be valid, parseable JSON</validation>
    <structure>Must exactly follow the schema_definition structure</structure>
    <completeness>Include all user-editable fields from the form</completeness>
    <accuracy>Field types and constraints must accurately reflect form elements</accuracy>
    <descriptions>Every section and field MUST have meaningful, action-oriented descriptions</descriptions>
    <restrictions>
        <restriction>Do not include ```json``` or any markdown formatting</restriction>
        <restriction>Do not include explanatory text outside the JSON</restriction>
        <restriction>Do not include comments within the JSON</restriction>
        <restriction>Do not include navigation elements or buttons</restriction>
        <restriction>Do not include display-only fields</restriction>
        <restriction>Always provide descriptions that explain what answer is needed, not just what the field is</restriction>
    </restrictions>
</output_rules>"""


def _extract_cache_stats(usage: Any) -> tuple[int, int]:
    """Extract cache statistics from LiteLLM usage object.

    Args:
        usage: LiteLLM usage object from response

    Returns:
        tuple[int, int]: (cache_read_tokens, cache_creation_tokens)
    """
    cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read = 0

    # Get cached_tokens from prompt_tokens_details (LiteLLM standard location)
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    if prompt_details:
        if isinstance(prompt_details, dict):
            cache_read = prompt_details.get("cached_tokens", 0) or 0
        else:
            cache_read = getattr(prompt_details, "cached_tokens", 0) or 0

    # Fallback: check for cache_read_input_tokens direct attribute
    if not cache_read:
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

    return cache_read, cache_creation


class SchemaGenerator:
    """AI-powered form schema generation service using LiteLLM."""

    def __init__(self) -> None:
        """Initialize schema generator with configuration."""
        _initialize_langfuse()

        config = get_config()
        self.model_name = config.ai.schema_model
        self.temperature = config.ai.temperature
        self.max_tokens = config.ai.max_tokens
        self.timeout = config.ai.timeout
        self.enable_cache = config.ai.enable_cache
        self.api_key = config.openrouter.api_key
        self.site_url = config.openrouter.site_url
        self.app_name = config.openrouter.app_name

        logger.info(
            "schema_generator_initialized",
            model=self.model_name,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            cache_enabled=self.enable_cache,
        )

    def _build_messages(
        self,
        screenshot_b64: str,
        image_type: str,
        prompt_text: str,
    ) -> list[dict[str, Any]]:
        """Build messages for LiteLLM completion call.

        Args:
            screenshot_b64: Base64-encoded screenshot
            image_type: MIME type of image (image/png or image/jpeg)
            prompt_text: User prompt text

        Returns:
            list[dict]: Messages for LiteLLM
        """
        # Add JSON schema instruction to system prompt
        json_instruction = (
            f"\n\nYou MUST respond with valid JSON matching this schema:\n"
            f"{FormSchema.model_json_schema()}"
        )
        full_system_prompt = SCHEMA_GENERATION_SYSTEM_PROMPT + json_instruction

        # Build system message with cache control for Anthropic caching
        if self.enable_cache:
            system_message: dict[str, Any] = {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": full_system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            }
        else:
            system_message = {"role": "system", "content": full_system_prompt}

        # Build user message with image
        user_message: dict[str, Any] = {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt_text},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{image_type};base64,{screenshot_b64}"},
                },
            ],
        }

        return [system_message, user_message]

    async def generate_schema(
        self,
        screenshot_bytes: bytes,
        sequence_number: int,
        session_id: str,
        scraped_facts: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[FormSchema, dict[str, Any]]:
        """Generate form schema from screenshot using AI vision.

        Args:
            screenshot_bytes: Screenshot image bytes
            sequence_number: Quartet sequence number
            session_id: Session identifier for logging
            scraped_facts: Optional scraped facts text to enhance schema generation
            metadata: Optional metadata dictionary containing url and timestamp

        Returns:
            tuple[FormSchema, dict]: Form schema and metrics dictionary

        Raises:
            ValueError: If AI response is invalid
            Exception: If AI operation fails
        """
        start_time = time.time()

        try:
            # Resize image if needed to meet API limits (8000x8000 pixels, 10MB)
            resized_bytes, resize_metadata = resize_image_for_vision_api(
                screenshot_bytes, max_dimension=8000, max_file_size_bytes=10 * 1024 * 1024
            )

            logger.debug(
                "image_resize_check",
                original_size=f"{resize_metadata['original_width']}x{resize_metadata['original_height']}",
                new_size=f"{resize_metadata['new_width']}x{resize_metadata['new_height']}",
                resized=resize_metadata["resized"],
                within_limits=resize_metadata["within_api_limits"],
                file_size_mb=resize_metadata["file_size_bytes"] / (1024 * 1024),
            )

            # Encode screenshot to base64
            screenshot_b64 = base64.b64encode(resized_bytes).decode("utf-8")

            # Determine image type (PNG or JPEG) from resized bytes
            if resized_bytes.startswith(b"\x89PNG"):
                image_type = "image/png"
            elif resized_bytes.startswith(b"\xff\xd8\xff"):
                image_type = "image/jpeg"
            else:
                raise ValueError("Unsupported image format (expected PNG or JPEG)")

            # Create vision message with image, URL, and timestamp
            page_url = metadata.get("url", "unknown") if metadata else "unknown"
            timestamp = metadata.get("timestamp", "unknown") if metadata else "unknown"
            prompt_text = f"Analyze the screenshot I've provided. URL: {page_url}, Captured at: {timestamp}"

            # Add scraped facts if provided
            if scraped_facts:
                prompt_text += f"""

Use the following enhancement information to improve the generated JSON schema by:

1. **Setting Required Flags**: Analyze the enhancement information to identify which fields are marked as required, mandatory, or have asterisks (*). Update the "required" property for these fields to true.

2. **Adding Visibility Rules**: Look for conditional field visibility patterns in the enhancement information such as:
   - Fields that appear/hide based on other field values
   - Sections that show/hide based on user selections
   - Conditional logic like "Show X when Y is selected" or "Display field A if field B equals value C"

   For each conditional field or section, populate the "visibility_rules" array with objects containing:
   - "field": The name of the field this condition depends on
   - "operator": The comparison operator (equals, notEquals, contains, greaterThan, lessThan)
   - "value": The value that triggers visibility

Examples of visibility rules:
- If "provideEmergencyContact" field equals "Yes", show emergency contact fields
- If "hasSpouse" checkbox is true, show spouse details section
- If "age" field is greaterThan 18, show adult consent fields

<enhancement_information>
{scraped_facts}
</enhancement_information>"""

            # Log the request being sent (without base64 image data)
            logger.info(
                "ai_request_sending",
                session_id=session_id,
                sequence_number=sequence_number,
                prompt=prompt_text[:200] + "..." if len(prompt_text) > 200 else prompt_text,
                image_type=image_type,
                image_size_bytes=len(screenshot_bytes),
                model=self.model_name,
                temperature=self.temperature,
            )

            # Build messages
            messages = self._build_messages(screenshot_b64, image_type, prompt_text)

            # Call LiteLLM with OpenRouter
            response = await acompletion(
                model=self.model_name,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                api_key=self.api_key,
                timeout=self.timeout,
                # LangFuse metadata for trace grouping
                metadata={
                    "operation": "schema_generation",
                    "session_id": session_id,
                    "sequence_number": sequence_number,
                },
                # OpenRouter headers
                extra_headers={
                    "HTTP-Referer": self.site_url,
                    "X-Title": self.app_name,
                },
                # OpenRouter requires usage.include=true to return cache statistics
                extra_body={
                    "usage": {"include": True},
                },
            )

            # Extract response text
            response_text = response.choices[0].message.content

            logger.debug(
                "ai_response_received_raw",
                text_length=len(response_text) if response_text else 0,
                text_preview=response_text[:200] if response_text else None,
            )

            # Handle different stop reasons
            if hasattr(response.choices[0], "finish_reason"):
                finish_reason = response.choices[0].finish_reason
                if finish_reason == "length":
                    logger.warning(
                        "response_truncated",
                        message="Response hit max_tokens limit, may be truncated",
                        max_tokens=self.max_tokens,
                    )

            # Strip markdown code fences if present
            cleaned_text = response_text.strip() if response_text else ""
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:]
            elif cleaned_text.startswith("```"):
                cleaned_text = cleaned_text[3:]
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3]
            cleaned_text = cleaned_text.strip()

            # Parse JSON and validate with Pydantic
            json_data = json.loads(cleaned_text)
            form_schema = FormSchema.model_validate(json_data)

            # Extract metrics from response
            usage = response.usage
            cache_read, cache_creation = _extract_cache_stats(usage)

            latency_ms = (time.time() - start_time) * 1000
            metrics = {
                "model": self.model_name,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.prompt_tokens + usage.completion_tokens,
                "cache_read_tokens": cache_read,
                "cache_creation_tokens": cache_creation,
                "latency_ms": latency_ms,
                "cost_usd": None,
            }

            logger.info(
                "token_usage",
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                cache_read=cache_read,
                cache_creation=cache_creation,
            )

            # Log the AI response
            logger.info(
                "ai_response_received",
                session_id=session_id,
                sequence_number=sequence_number,
                page_identifier=form_schema.page_identifier,
                form_name=form_schema.form_name,
                sections_count=len(form_schema.sections),
                total_fields=sum(len(section.fields) for section in form_schema.sections),
            )

            # Log operation
            log_ai_operation(
                logger,
                operation="schema_generation",
                model=self.model_name,
                prompt_tokens=metrics["prompt_tokens"],
                completion_tokens=metrics["completion_tokens"],
                total_tokens=metrics["total_tokens"],
                latency_ms=latency_ms,
                prompt_preview=f"Screenshot schema analysis for sequence {sequence_number}",
            )

            logger.info(
                "schema_generation_complete",
                session_id=session_id,
                sequence_number=sequence_number,
                sections_count=len(form_schema.sections),
                total_fields=sum(len(section.fields) for section in form_schema.sections),
                latency_ms=latency_ms,
            )

            return form_schema, metrics

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000

            logger.error(
                "schema_generation_failed",
                session_id=session_id,
                sequence_number=sequence_number,
                error=str(e),
                latency_ms=latency_ms,
                exc_info=True,
            )

            raise


# Global instance
_schema_generator: SchemaGenerator | None = None


def get_schema_generator() -> SchemaGenerator:
    """Get or create global schema generator instance.

    Returns:
        SchemaGenerator: Configured schema generator
    """
    global _schema_generator

    if _schema_generator is None:
        _schema_generator = SchemaGenerator()

    return _schema_generator


def reset_schema_generator() -> None:
    """Reset global schema generator (useful for testing)."""
    global _schema_generator
    _schema_generator = None
