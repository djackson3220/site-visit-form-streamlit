import os
import tempfile
from datetime import datetime

import requests
import streamlit as st
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from zoneinfo import ZoneInfo  # ← For Albuquerque timezone


# ────────────────────────────────────────────────────────────────────────────────
#  1) Page config
# ────────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Site Visit Report", layout="centered")


# ────────────────────────────────────────────────────────────────────────────────
#  2) Helper: fetch current temperature for Albuquerque, NM
# ────────────────────────────────────────────────────────────────────────────────

def get_current_temperature(api_key: str) -> str:
    """
    Uses OpenWeatherMap API to fetch the current temp (°F) in Albuquerque, NM.
    Returns a one‐decimal string (e.g. "75.2"), or "N/A" on any error.
    """
    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": "Albuquerque,US",
            "units": "imperial",   # returns °F
            "appid": api_key,
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if resp.status_code == 200 and "main" in data:
            temp_f = data["main"].get("temp")
            if isinstance(temp_f, (int, float)):
                return f"{temp_f:.1f}"
        return "N/A"
    except Exception:
        return "N/A"


# ────────────────────────────────────────────────────────────────────────────────
#  3) Helper: generate PDF with embedded images + survey + temp/time
# ────────────────────────────────────────────────────────────────────────────────

def generate_pdf(
    visitor: str,
    visit_date: str,
    site_address: str,
    summary: str,
    survey_responses: dict,
    image_files_batch1,
    image_files_batch2,
    api_key: str,
) -> bytes:
    """
    Creates a PDF recording:
      • Current timestamp (ABQ local time)
      • Albuquerque temperature (if api_key is valid; otherwise "N/A")
      • Visitor name, visit_date, site_address, summary
      • Survey answers (9 questions)
      • Up to 8 images (two batches of 4)
    Returns the PDF bytes.
    """
    # 1) Fetch current time & temperature (inside PDF as well)
    abq_tz = ZoneInfo("America/Denver")
    now_abq = datetime.now(abq_tz).strftime("%Y-%m-%d %H:%M:%S")
    temp_str = get_current_temperature(api_key) if api_key else "N/A"

    # 2) Create a temporary file for the PDF
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp_pdf_path = tmp.name
    tmp.close()

    c = canvas.Canvas(tmp_pdf_path, pagesize=letter)
    width, height = letter  # 612 x 792 points

    # ── Header: Title ────────────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 18)
    c.drawString(200, height - 50, "Site Visit Report")

    # ── Time & Temperature ───────────────────────────────────────────────────────
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 80, f"Generated At (ABQ) : {now_abq}")
    c.drawString(50, height - 95, f"Temperature (°F)  : {temp_str}")

    # ── Divider ───────────────────────────────────────────────────────────────────
    c.line(50, height - 105, width - 50, height - 105)

    # ── Visitor, Date, Address ───────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 125, "Visitor Name      :")
    c.setFont("Helvetica", 12)
    c.drawString(200, height - 125, visitor)

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 145, "Date of Visit     :")
    c.setFont("Helvetica", 12)
    c.drawString(200, height - 145, visit_date)

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 165, "Site Address      :")
    c.setFont("Helvetica", 12)
    c.drawString(200, height - 165, site_address)

    # ── Divider ───────────────────────────────────────────────────────────────────
    c.line(50, height - 175, width - 50, height - 175)

    # ── Brief Summary ─────────────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 195, "Brief Summary:")
    text_obj = c.beginText(50, height - 215)
    text_obj.setFont("Helvetica", 11)
    for line in summary.split("\n"):
        text_obj.textLine(line)
    c.drawText(text_obj)

    # Compute where to start drawing the survey
    summary_lines = summary.count("\n") + 1
    survey_y_start = height - 215 - (summary_lines * 12) - 20

    # ── Survey Questions ─────────────────────────────────────────────────────────
    if survey_y_start < 200:
        c.showPage()
        survey_y_start = height - 100

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, survey_y_start, "Survey Responses:")

    c.setFont("Helvetica", 11)
    line_height = 14
    y = survey_y_start - 20

    survey_questions = {
        "Q1": "1) Did weather cause any delays?",
        "Q2": "2) Any instruction Contractor and Contractor’s actions?",
        "Q3": "3) Any general comments or unusual events?",
        "Q4": "4) Any schedule delays occur?",
        "Q5": "5) Materials on site?",
        "Q6": "6) Contractor and Subcontractor Equipment onsite?",
        "Q7": "7) Testing?",
        "Q8": "8) Any visitors on site?",
        "Q9": "9) Any accidents on site today?",
    }

    for key, question in survey_questions.items():
        answer = survey_responses.get(key, "N/A")
        c.drawString(60, y, f"{question}   ▶ {answer}")
        y -= line_height

    # ── Images ─────────────────────────────────────────────────────────────────────
    if y < 200:
        c.showPage()
        y = height - 100

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Site Photos:")
    y -= 20

    def draw_images_at(start_x, start_y, files):
        x = start_x
        max_h = 0
        for uploaded in files or []:
            try:
                img = ImageReader(uploaded)
                iw, ih = img.getSize()
                scale = 200.0 / float(iw)
                scaled_w = 200
                scaled_h = ih * scale

                # Wrap if beyond right margin
                if x + scaled_w > width - 50:
                    x = start_x
                    start_y -= (max_h + 20)
                    max_h = 0

                c.drawImage(img, x, start_y - scaled_h, width=scaled_w, height=scaled_h)
                x += scaled_w + 20
                max_h = max(max_h, scaled_h)
            except Exception:
                continue

        return start_y - max_h - 20

    # Draw batch 1
    y = draw_images_at(50, y, image_files_batch1)
    # Draw batch 2
    if image_files_batch2:
        if y < 100:
            c.showPage()
            y = height - 100
        y = draw_images_at(50, y, image_files_batch2)

    # ── Finalize and return PDF bytes ─────────────────────────────────────────────
    c.save()
    with open(tmp_pdf_path, "rb") as f:
        pdf_bytes = f.read()
    os.remove(tmp_pdf_path)
    return pdf_bytes


# ────────────────────────────────────────────────────────────────────────────────
#  4) Streamlit UI
# ────────────────────────────────────────────────────────────────────────────────

st.title("Site Visit Report 📋")

# 4.a) Basic form fields
visitor_name = st.text_input("Your Name", max_chars=50)
visit_date   = st.date_input("Date of Visit", value=datetime.today())
site_address = st.text_input("Site Address / Location", max_chars=100)
summary      = st.text_area(
    "Brief Summary",
    help="Describe what you saw/did on site. (Hit Enter for new lines.)",
    height=120,
)

# 4.b) Survey questions
st.markdown("---")
st.header("Survey")
survey_answers = {}
survey_answers["Q1"] = st.radio(
    "1) Did weather cause any delays?",
    ("N/A", "No", "Yes"),
    index=0,
    horizontal=True,
)
survey_answers["Q2"] = st.radio(
    "2) Any instruction Contractor and Contractor’s actions?",
    ("N/A", "No", "Yes"),
    index=0,
    horizontal=True,
)
survey_answers["Q3"] = st.radio(
    "3) Any general comments or unusual events?",
    ("N/A", "No", "Yes"),
    index=0,
    horizontal=True,
)
survey_answers["Q4"] = st.radio(
    "4) Any schedule delays occur?",
    ("N/A", "No", "Yes"),
    index=0,
    horizontal=True,
)
survey_answers["Q5"] = st.radio(
    "5) Materials on site?",
    ("N/A", "No", "Yes"),
    index=0,
    horizontal=True,
)
survey_answers["Q6"] = st.radio(
    "6) Contractor and Subcontractor Equipment onsite?",
    ("N/A", "No", "Yes"),
    index=0,
    horizontal=True,
)
survey_answers["Q7"] = st.radio(
    "7) Testing?",
    ("N/A", "No", "Yes"),
    index=0,
    horizontal=True,
)
survey_answers["Q8"] = st.radio(
    "8) Any visitors on site?",
    ("N/A", "No", "Yes"),
    index=0,
    horizontal=True,
)
survey_answers["Q9"] = st.radio(
    "9) Any accidents on site today?",
    ("N/A", "No", "Yes"),
    index=0,
    horizontal=True,
)

# 4.c) Image uploads: two separate batches of up to 4 each
st.markdown("---")
st.header("Site Photos")
image_files_batch1 = st.file_uploader(
    "Upload images (batch 1 of 2, up to 4 pics)",
    type=["png", "jpg", "jpeg"],
    accept_multiple_files=True,
    key="batch1",
)
if image_files_batch1 and len(image_files_batch1) > 4:
    st.warning("Please only upload up to 4 images in this batch.")
    image_files_batch1 = image_files_batch1[:4]

image_files_batch2 = st.file_uploader(
    "Upload images (batch 2 of 2, up to 4 pics)",
    type=["png", "jpg", "jpeg"],
    accept_multiple_files=True,
    key="batch2",
)
if image_files_batch2 and len(image_files_batch2) > 4:
    st.warning("Please only upload up to 4 images in this batch.")
    image_files_batch2 = image_files_batch2[:4]

# 4.d) Ask for OpenWeatherMap API key (optional)
st.markdown("---")
st.info(
    "If you want the PDF to include today’s Albuquerque temperature, enter your OpenWeatherMap API key. "
    "Otherwise, temperature will show as “N/A.”"
)
owm_api_key = st.text_input(
    "OpenWeatherMap API Key",
    type="password",
    help="Get a free key at https://openweathermap.org/ → Sign Up → API Keys",
)

# 4.e) Display the current time (ABQ) and (conditionally) temperature on the page
abq_tz = ZoneInfo("America/Denver")
now_abq = datetime.now(abq_tz).strftime("%Y-%m-%d %H:%M:%S")
st.write(f"**Current Time (ABQ):** {now_abq}")

if owm_api_key:
    temp_display = get_current_temperature(owm_api_key)
    if temp_display != "N/A":
        st.write(f"**Current Temperature (°F):** {temp_display}")
    else:
        st.info("Unable to fetch temperature. Check your API key or network.")
else:
    st.info("No API key provided → temperature will be ‘N/A’ in PDF.")

# 4.f) Button to generate the PDF
st.markdown("---")
generate_pdf_button = st.button("Generate PDF")

if generate_pdf_button:
    missing = []
    if not visitor_name.strip():
        missing.append("– Visitor Name is required.")
    if not site_address.strip():
        missing.append("– Site Address is required.")
    if not summary.strip():
        missing.append("– Brief Summary is required.")

    if missing:
        st.error(
            "Please fill in the following fields before generating the PDF:\n"
            + "\n".join(missing)
        )
    else:
        try:
            with st.spinner("Creating PDF..."):
                pdf_bytes = generate_pdf(
                    visitor=visitor_name,
                    visit_date=visit_date.strftime("%Y/%m/%d"),
                    site_address=site_address,
                    summary=summary,
                    survey_responses=survey_answers,
                    image_files_batch1=image_files_batch1,
                    image_files_batch2=image_files_batch2,
                    api_key=owm_api_key,
                )
        except Exception as e:
            st.error("🚨 Internal error while generating PDF:\n\n" + repr(e))
        else:
            timestamp = datetime.now(abq_tz).strftime("%Y%m%d_%H%M%S")
            default_filename = f"site_visit_report_{timestamp}.pdf"
            st.success("PDF generated successfully!")
            st.download_button(
                label="Download PDF",
                data=pdf_bytes,
                file_name=default_filename,
                mime="application/pdf",
            )
