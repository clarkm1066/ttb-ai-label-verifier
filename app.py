import os
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from utils.verification_engine import verify_label_compliance

# --- API Key Setup ---
# Local dev: reads from .env file
# Streamlit Cloud: reads from the Secrets manager in the dashboard
load_dotenv()
if "OPENAI_API_KEY" in st.secrets:
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]

st.set_page_config(page_title="Alcohol Label Auditor", layout="wide")
st.title("🔍 Alcohol Label Compliance Auditor")

# --- Session state for form reset and result storage ---
if "audit_key" not in st.session_state:
    st.session_state.audit_key = 0
if "audit_result" not in st.session_state:
    st.session_state.audit_result = None
if "audit_image" not in st.session_state:
    st.session_state.audit_image = None

# --- UI Setup ---
tab1, tab2 = st.tabs(["Single Label Audit", "Batch Processing"])


# --- Helper Function for Display ---
def display_results(results):
    if not results:
        st.warning("No results to display.")
        return

    # Handle error results returned by the engine
    if results.get("error"):
        st.error(f"Analysis failed: {results.get('error')}")
        return

    # Extraction mode returns {"data": {...}} instead of audit fields
    if "data" in results and "overall_status" not in results:
        st.info("**Extraction Mode** — no application data provided. Fields extracted from label:")
        st.divider()
        for field, value in results["data"].items():
            st.write(f"**{field.replace('_', ' ').title()}:** {value}")
        return

    overall = results.get("overall_status", "N/A")
    color = "green" if overall == "COMPLIANT" else "red"
    st.markdown(f"**Verdict:** :{color}[{overall}]")
    st.write(f"**Notes:** {results.get('auditor_notes', 'N/A')}")

    check_data = results.get("checks", {})
    if check_data:
        st.divider()
        for check, data in check_data.items():
            if isinstance(data, dict):
                status = data.get("status", "N/A")
                details = data.get("details", "")
            else:
                status = "PASS"
                details = str(data)

            if status == "PASS":
                icon = "✅"
            elif status == "WARN":
                icon = "⚠️"
            else:
                icon = "❌"

            st.write(f"{icon} **{check.replace('_', ' ').title()}**: {details}")


# --- Tab 1: Single Label Audit ---
with tab1:
    st.header("Single Label Audit")

    # Clear button appears at top once results are ready
    if st.session_state.audit_result is not None:
        if st.button("🔄 Start New Audit"):
            st.session_state.audit_result = None
            st.session_state.audit_image = None
            st.session_state.audit_key += 1
            st.rerun()

    with st.form(key=f"single_label_form_{st.session_state.audit_key}"):
        col1, col2 = st.columns(2)
        with col1:
            brand_name = st.text_input("Brand Name")
            class_type = st.text_input("Product Type/Class")
            abv = st.text_input("ABV %")
        with col2:
            proof = st.text_input("Proof")
            net_contents = st.text_input("Net Contents")
            bottler = st.text_input("Bottler Info")
            origin = st.text_input("Country of Origin")

        uploaded_file = st.file_uploader("Upload Label Image", type=["jpg", "jpeg", "png"],
                                         key=f"uploader_{st.session_state.audit_key}")
        submit = st.form_submit_button("Check Label Compliance")

    if submit and uploaded_file:
        app_data = {
            "brand_name": brand_name,
            "class_type": class_type,
            "abv": abv,
            "proof": proof,
            "net_contents": net_contents,
            "bottler_info": bottler,
            "country_of_origin": origin,
        }
        with st.spinner("Analyzing..."):
            image_bytes = uploaded_file.read()
            result = verify_label_compliance(image_bytes, uploaded_file.name, app_data)
        st.session_state.audit_result = result
        st.session_state.audit_image = image_bytes
        st.rerun()

    elif submit and not uploaded_file:
        st.warning("Please upload a label image before submitting.")

    # Display stored results
    if st.session_state.audit_result is not None:
        st.image(st.session_state.audit_image, width=400, caption="Label Preview")
        display_results(st.session_state.audit_result)


# --- Tab 2: Batch Processing ---
with tab2:
    st.header("Batch Processing")
    st.caption(
        "Upload a manifest CSV and one or more label images together. "
        "The CSV must have a **filename** column that matches the image filenames."
    )
    uploaded_items = st.file_uploader(
        "Upload CSV & Label Images",
        type=["csv", "jpg", "jpeg", "png"],
        accept_multiple_files=True,
    )

    if st.button("Run Batch Audit"):
        if not uploaded_items:
            st.warning("Please upload at least one image (and optionally a manifest CSV).")
        else:
            manifest_data = {}
            label_images = []  # list of (name, bytes) tuples

            # Parse uploaded items — read bytes immediately so streams aren't spent
            for item in uploaded_items:
                if item.name.lower().endswith(".csv"):
                    df = pd.read_csv(item)
                    df.columns = [c.strip().lower() for c in df.columns]
                    if "filename" in df.columns:
                        for _, row in df.iterrows():
                            manifest_data[str(row["filename"]).strip()] = row.to_dict()
                    else:
                        st.warning(
                            f"CSV '{item.name}' has no 'filename' column — skipping manifest."
                        )
                else:
                    label_images.append((item.name, item.read()))

            if not label_images:
                st.warning("No label images found in the uploaded files.")
            else:
                with st.spinner(f"Analyzing {len(label_images)} label(s)..."):

                    def process(name_bytes):
                        name, img_bytes = name_bytes
                        data = manifest_data.get(name, {})
                        result = verify_label_compliance(img_bytes, name, data)
                        return {"name": name, "img_bytes": img_bytes, "results": result}

                    # Cap concurrency to avoid API rate limits on large batches
                    max_workers = min(10, len(label_images))
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        results = list(executor.map(process, label_images))

                tabs = st.tabs([r["name"] for r in results])
                for i, tab in enumerate(tabs):
                    with tab:
                        st.image(results[i]["img_bytes"], width=400)
                        display_results(results[i]["results"])
