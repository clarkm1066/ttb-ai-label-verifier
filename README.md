# TTB Alcohol Label Compliance Auditor

An AI-powered prototype that helps compliance agents validate alcohol beverage labels against TTB regulatory requirements. Upload a label image, provide the application metadata, and the tool instantly flags mismatches, missing fields, and government warning violations.

---

## 🌐 Live Demo

**[https://YOUR-APP-NAME.streamlit.app](https://YOUR-APP-NAME.streamlit.app)**

> No installation required. Open the link above in any browser to begin testing.

---

## 🧪 Evaluator Quick Start

A set of ready-made test labels and form data is included in the `test_labels/` folder of this repository. The Word document `TTB_Test_Label_Data.docx` contains the exact form field values for each label and the expected result.

### Single Label Audit

1. Open the live demo link above
2. Make sure you are on the **Single Label Audit** tab
3. Download a label image from `test_labels/` (e.g., `label_01_compliant_bourbon.png`)
4. Enter the corresponding field values from `TTB_Test_Label_Data.docx`
5. Click **Upload Label Image** and select the image file
6. Click **Check Label Compliance**
7. Results appear immediately below — no extra clicks required

### Batch Processing

The `test_labels/manifest folder/` directory contains a ready-to-run batch test with two compliant labels and a pre-filled manifest CSV.

1. Click the **Batch Processing** tab
2. Click the file uploader and select **all three files at once** from `test_labels/manifest folder/`:
   - `manifest.csv` — contains the application metadata for each label
   - `Perfect Label_1.jpeg`
   - `Perfect Label_2.png`
3. Click **Run Batch Audit**
4. Two result tabs will appear — click each to review the audit findings for that label

> **How the manifest works:** The CSV `filename` column must match the uploaded image filenames exactly. The app automatically maps each image to its row of application data. If no CSV is uploaded, all images run in Extraction Mode instead.

---

## 🔬 Test Scenarios

Six test labels cover the full range of compliance outcomes. All images and form data are in `test_labels/TTB_Test_Label_Data.docx`.

| # | File | What It Tests | Expected Result |
|---|------|--------------|-----------------|
| 1 | `label_01_compliant_bourbon.png` | All fields correct, warning verbatim | ✅ COMPLIANT |
| 2 | `label_02_wrong_abv_rye.png` | ABV on label (40%) vs. form entry (45%) | ❌ NON-COMPLIANT — ABV mismatch |
| 3 | `label_03_bad_warning_vodka.png` | Warning in title case, not ALL CAPS | ❌ NON-COMPLIANT — warning violation |
| 4 | `label_04_brand_case_gin.png` | Label ALL CAPS vs. mixed-case form entry | ⚠️ WARN — human review recommended |
| 5 | `label_05_missing_fields_rum.png` | No bottler or country of origin | ⚠️ WARN — fields unverifiable |
| 6 | `label_06_extraction_tequila.png` | Leave all form fields **blank** | Extracted field data (Extraction Mode) |

---

## 📐 Technical Approach

### Architecture

```
app.py  (Streamlit frontend)
    │
    └── utils/verification_engine.py  (Vision LLM backend)
            │
            └── OpenAI GPT-4o (Vision)
```

The frontend and backend are intentionally decoupled. `app.py` handles all UI state, file I/O, and parallel orchestration. `verification_engine.py` is a stateless function that accepts image bytes and application data and returns a structured JSON result — it has no Streamlit dependency and can be called from any context.

### Dual-Mode Operation

The engine automatically selects a mode based on whether form data is provided:

- **Audit Mode** — compares label text against the provided application metadata field by field. Returns `overall_status`, `auditor_notes`, and a per-field `checks` object with `PASS`, `WARN`, or `FAIL` status.
- **Extraction Mode** — when no application data is provided, extracts and transcribes all visible label fields. Useful when reviewing labels without a corresponding application on file.

### Government Warning Verification

The full verbatim TTB warning statement (27 CFR § 16.21) is embedded in the system prompt. The model is explicitly instructed to:

- Verify exact wording — no paraphrasing or truncation
- Require `GOVERNMENT WARNING:` in ALL CAPS
- Flag title-case variants (`Government Warning:`) as a hard failure
- Flag unreadable or excessively small warning text as a failure

### Compliance Check Logic

| Field | Behavior |
|-------|----------|
| Government Warning | Exact verbatim match required; any deviation is FAIL |
| Brand Name | Case-only differences return WARN (human review); substantive differences return FAIL |
| ABV | Numeric value must match; formatting differences (e.g., "45%" vs "45% Alc./Vol.") are accepted |
| Net Contents | Equivalent representations accepted (e.g., "750 mL" = "750ml") |
| Class/Type, Bottler, Origin | Substantive mismatches return FAIL; absent data returns WARN |

### Performance

Parallel processing via `ThreadPoolExecutor` (capped at 10 concurrent workers) handles batch uploads. Single-label audits typically complete in 2–4 seconds using GPT-4o. Images are preprocessed and resized before encoding to minimize token usage and latency.

### Error Handling

All failure points are caught and returned as structured error objects rather than unhandled exceptions:

- Image preprocessing failures (corrupt or unreadable files)
- OpenAI API errors (auth failures, rate limits, timeouts)
- Malformed JSON in model responses

---

## 💡 Design Decisions & Assumptions

**Why GPT-4o?** It provides the best combination of vision accuracy and response speed for this use case. The `temperature=0` setting ensures deterministic, consistent results across repeated audits of the same label.

**Why Streamlit?** The brief called for a tool that agents with varying technical backgrounds can use without training. Streamlit provides a clean, browser-based interface with no installation required for end users, and deploys in minutes.

**Brand name case sensitivity** — per feedback from senior compliance agents, a label reading `STONE'S THROW` when the application says `Stone's Throw` is almost always the same product. The system returns a `WARN` rather than a hard `FAIL` and recommends human review, reducing unnecessary rejections while still flagging the discrepancy.

**ABV formatting tolerance** — labels commonly express alcohol content in multiple valid formats (`45%`, `45% Alc./Vol.`, `90 Proof`). The system checks the numeric value rather than requiring an exact string match.

**CSV manifest normalization** — column headers are lowercased and whitespace-stripped automatically. Importers frequently submit inconsistent spreadsheet formatting; this prevents the batch processor from failing on trivially malformed input.

**Proof field** — included in the form to match real TTB application structure. The model receives both ABV and proof values and can cross-validate them (proof = 2× ABV).

**Known limitation — image quality** — very low resolution, heavily glared, or severely angled label photographs may reduce extraction accuracy. In production, agents should be prompted to resubmit clearer images; the current prototype flags unreadable fields rather than guessing.

---

## 🛠 Local Setup

### Prerequisites

- Python 3.9 or higher
- An OpenAI API key with access to GPT-4o

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/YOUR-USERNAME/ttb-ai-label-verifier.git
cd ttb-ai-label-verifier

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create a .env file with your API key
echo "OPENAI_API_KEY=your_key_here" > .env

# 4. Run the app
streamlit run app.py
```

The app will open automatically at `http://localhost:8501`.

### Project Structure

```
ttb-ai-label-verifier/
├── app.py                  # Streamlit frontend
├── utils/
│   └── verification_engine.py  # Vision LLM backend
├── test_labels/            # Sample labels and evaluator reference doc
│   ├── TTB_Test_Label_Data.docx      # Form data + expected results for each test
│   ├── label_01_compliant_bourbon.png
│   ├── label_02_wrong_abv_rye.png
│   ├── label_03_bad_warning_vodka.png
│   ├── label_04_brand_case_gin.png
│   ├── label_05_missing_fields_rum.png
│   ├── label_06_extraction_tequila.png
│   └── manifest folder/              # Ready-to-run batch test
│       ├── manifest.csv              # Application metadata for both labels
│       ├── Perfect Label_1.jpeg
│       └── Perfect Label_2.png
├── requirements.txt
├── .env                    # Not committed — create locally
└── .gitignore
```

---

## 📋 TTB Mandatory Label Fields

Per TTB regulations, the following fields are verified on every label:

- **Brand Name** — must match application exactly (case differences flagged for review)
- **Class/Type Designation** — e.g., "Kentucky Straight Bourbon Whiskey"
- **Alcohol Content** — percentage by volume; numeric value must match
- **Net Contents** — e.g., "750 mL"
- **Bottler/Producer Name and Address**
- **Country of Origin** (imports)
- **Government Health Warning Statement** — verbatim, per 27 CFR § 16.21

---

*Built as a take-home prototype for the TTB Compliance Division AI evaluation.*
