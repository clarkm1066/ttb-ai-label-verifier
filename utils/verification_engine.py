import json
import base64
import io
from PIL import Image
from openai import OpenAI, OpenAIError
import os

# ---------------------------------------------------------------------------
# Full verbatim TTB government warning statement (27 CFR 16.21)
# ---------------------------------------------------------------------------
GOVERNMENT_WARNING_TEXT = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not "
    "drink alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)

AUDIT_SYSTEM_PROMPT = f"""You are a strict TTB (Alcohol and Tobacco Tax and Trade Bureau) compliance auditor.
Your job is to compare the text visible on a label image against the provided Application Data and TTB regulations.

GOVERNMENT WARNING RULE — this is your most important check:
- The label MUST include the following statement, verbatim:
  "{GOVERNMENT_WARNING_TEXT}"
- The prefix "GOVERNMENT WARNING:" MUST appear in ALL CAPS.
- The full statement must not be truncated, paraphrased, or reworded in any way.
- Title-case ("Government Warning:"), missing sentences, or changed wording are ALL failures.
- If the warning text appears too small to read clearly from the image, flag it as a FAIL with a note.

BRAND NAME RULE:
- Compare the brand name on the label to the Application Data brand name.
- If they match exactly (including case), it is a PASS.
- If they differ only in capitalization (e.g., "STONE'S THROW" vs "Stone's Throw", or "COPPER STILL" vs "Copper Still"),
  you MUST return status "WARN" with details noting the case difference and recommending human review.
  Do NOT return PASS when capitalization differs — a WARN is required.
- If the text is substantively different, return "FAIL".

OTHER FIELD RULES:
- ABV: the percentage on the label must match the application value. Accept minor formatting differences
  (e.g., "45%" vs "45% Alc./Vol.") but flag numeric mismatches as FAIL.
- Net Contents: must match application value. Accept equivalent representations (e.g., "750 mL" = "750ml").
- Class/Type, Bottler Info, Country of Origin: flag any substantive mismatch as FAIL.

OUTPUT FORMAT — respond with a JSON object only, no prose:
{{
  "overall_status": "COMPLIANT" | "NON-COMPLIANT",
  "auditor_notes": "<brief summary of findings>",
  "checks": {{
    "brand_name":        {{"status": "PASS"|"WARN"|"FAIL", "details": "<string>"}},
    "class_type":        {{"status": "PASS"|"WARN"|"FAIL", "details": "<string>"}},
    "abv":               {{"status": "PASS"|"WARN"|"FAIL", "details": "<string>"}},
    "net_contents":      {{"status": "PASS"|"WARN"|"FAIL", "details": "<string>"}},
    "bottler_info":      {{"status": "PASS"|"WARN"|"FAIL", "details": "<string>"}},
    "country_of_origin": {{"status": "PASS"|"WARN"|"FAIL", "details": "<string>"}},
    "government_warning":{{"status": "PASS"|"WARN"|"FAIL", "details": "<string>"}}
  }}
}}

MISSING FIELD RULES — this distinction is critical:
- If a mandatory field is NOT VISIBLE on the label at all → "FAIL" (missing required field)
- If a mandatory field IS visible on the label but no Application Data was provided to compare against → "WARN" (present but unverifiable)
- Mandatory fields that must be physically present on every label: brand_name, class_type, abv, net_contents, bottler_info, government_warning
- country_of_origin is mandatory only for imported products; if the label indicates a domestic product it may be omitted without penalty

overall_status must be "NON-COMPLIANT" if ANY field is "FAIL".
overall_status must be "COMPLIANT" only if all mandatory fields are physically present on the label (WARN due to missing application data is acceptable for COMPLIANT).
auditor_notes must accurately summarize only the issues found in the checks object. Do not mention a problem in auditor_notes that is not reflected as FAIL or WARN in the checks. Do not omit a FAIL or WARN from the summary.
"""

EXTRACTION_SYSTEM_PROMPT = """You are a data extractor for TTB alcohol label compliance.
Extract all visible text fields from the label image and return them as structured JSON.

Return a JSON object with a single key "data" containing the extracted fields, for example:
{
  "data": {
    "brand_name": "...",
    "class_type": "...",
    "abv": "...",
    "proof": "...",
    "net_contents": "...",
    "bottler_info": "...",
    "country_of_origin": "...",
    "government_warning": "...",
    "other_text": "..."
  }
}

For the government_warning field, transcribe the exact text as it appears on the label, preserving capitalization.
If a field is not visible on the label, omit it from the output.
"""


def preprocess_image(image_bytes: bytes) -> bytes:
    """Resize and normalize image to reduce token usage while preserving readability."""
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode != "RGB":
        img = img.convert("RGB")
    max_size = 1500
    if max(img.size) > max_size:
        ratio = max_size / float(max(img.size))
        new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def verify_label_compliance(image_bytes: bytes, filename: str, application_data: dict) -> dict:
    """
    Verify a label image against application data using a Vision LLM.

    Args:
        image_bytes:      Raw bytes of the label image.
        filename:         Original filename (used for error messages).
        application_data: Dict of application fields (brand_name, abv, etc.).
                          If all values are empty/None, runs in Extraction mode.

    Returns:
        A dict with keys: overall_status, auditor_notes, checks  (Audit mode)
                       or: data                                   (Extraction mode)
                       or: error                                  (on failure)
    """
    mode = "audit" if any(v for v in application_data.values() if v) else "extraction"

    try:
        processed_bytes = preprocess_image(image_bytes)
    except Exception as e:
        return {"error": f"Image preprocessing failed for '{filename}': {e}"}

    encoded_image = base64.b64encode(processed_bytes).decode("utf-8")
    system_prompt = AUDIT_SYSTEM_PROMPT if mode == "audit" else EXTRACTION_SYSTEM_PROMPT

    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Application Data: {json.dumps(application_data)}",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{encoded_image}"
                            },
                        },
                    ],
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
    except OpenAIError as e:
        return {"error": f"API request failed for '{filename}': {e}"}

    try:
        return json.loads(response.choices[0].message.content)
    except (json.JSONDecodeError, IndexError, AttributeError) as e:
        return {"error": f"Failed to parse API response for '{filename}': {e}"}
