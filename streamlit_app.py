import os
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# ────────────────────────────────────────────────────────────────────────────────
# 1) Page Configuration
# ────────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Site Visit Report", layout="centered")


# ────────────────────────────────────────────────────────────────────────────────
# 2) Utility: Fetch Current Temperature in Albuquerque, NM (Open-Meteo API)
# ────────────────────────────────────────────────────────────────────────────────

def get_current_temperature_abq() -> str:
    """
    Fetches the current temperature (°F) at Albuquerque, NM (35.0844, -106.6504)
    using Open-Meteo’s public API. Returns a string like '74.2' or 'N/A' on failure.
    """
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": 35.0844,
            "longitude": -106.6504,
            "current_weather": True,
            "temperature_unit": "fahrenheit",
            "timezone": "America/Denver",
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if resp.status_code == 200 and "current_weather" in data:
            temp_f = data["current_weather"]["temperature"]
            return f"{temp_f:.1f}"
        else:
            return "N/A"
    except Exception:
        return "N/A"


# ────────────────────────────────────────────────────────────────────────────────
# 3) PDF Generation Function (Professional Layout)
# ────────────────────────────────────────────────────────────────────────────────

def generate_pdf(
    project_title: str,
    site_address: str,
    job_number: str,
    prepared_by: str,
    summary: str,
    survey_responses: dict,
    image_files_batch1,
    image_files_batch2,
):
    """
    Creates a professional PDF using ReportLab.  Layout:
     • Blue top banner with project_title (white, large) and site_address (white, smaller)
     • Black sub-banner with Date, Job #, Prepared By
     • “Weather” section in a light-blue rectangle
     • “Brief Summary” text block
     • “Survey” section as a table: question / chosen answer / comment
     • Up to 8 images (two batches of 4)
    """

    # 3.a) Fetch current ABQ time & temperature
    abq_tz = ZoneInfo("America/Denver")
    now_abq = datetime.now(abq_tz)
    now_abq_str = now_abq.strftime("%a %m/%d/%Y  %I:%M %p")
    temp_str = get_current_temperature_abq()

    # 3.b) Prepare a temporary file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp_path = tmp.name
    tmp.close()

    # 3.c) Create the canvas
    c = canvas.Canvas(tmp_path, pagesize=letter)
    width, height = letter

    # ─── Top Blue Banner ───────────────────────────────────────────────────────────
    banner_height = 80
    c.setFillColorRGB(0.12, 0.68, 0.80)  # light-blue
    c.rect(0, height - banner_height, width, banner_height, fill=1, stroke=0)

    # Project Title (white, bold, large)
    c.setFont("Helvetica-Bold", 24)
    c.setFillColor(colors.white)
    c.drawString(40, height - 45, project_title[:60])

    # Site Address (white, normal, smaller)
    c.setFont("Helvetica", 12)
    c.drawString(40, height - 65, site_address[:70])

    # ─── Black Sub-Banner (Date / Job # / Prepared By) ──────────────────────────────
    sub_banner_height = 30
    c.setFillColorRGB(0, 0, 0)  # black
    c.rect(0, height - banner_height - sub_banner_height, width, sub_banner_height, fill=1, stroke=0)

    # Text inside black bar (in white)
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.white)
    # Date on left
    c.drawString(40, height - banner_height - 20, f"Date: {now_abq_str}")
    # Job # centered
    c.drawCentredString(width / 2, height - banner_height - 20, f"Job #: {job_number}")
    # Prepared By on right
    c.drawRightString(width - 40, height - banner_height - 20, f"Prepared By: {prepared_by}")

    # ─── “Weather” Section (light-blue header + details) ────────────────────────────
    weather_top = height - banner_height - sub_banner_height - 40
    weather_header_height = 25
    c.setFillColorRGB(0.12, 0.68, 0.80)
    c.rect(0, weather_top, width, weather_header_height, fill=1, stroke=0)

    # “Weather” text
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(colors.white)
    c.drawString(40, weather_top + 7, "Weather (Albuquerque, NM)")

    # Weather details below header
    c.setFont("Helvetica", 11)
    c.setFillColor(colors.black)
    weather_label_y = weather_top - 20
    c.drawString(40, weather_label_y, f"Current Time (ABQ): {now_abq_str}")
    c.drawString(300, weather_label_y, f"Temperature (°F): {temp_str}")

    # ─── “Brief Summary” Section ───────────────────────────────────────────────────
    summary_top = weather_label_y - 30
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, summary_top, "Brief Summary:")

    text_object = c.beginText(40, summary_top - 18)
    text_object.setFont("Helvetica", 11)
    for line in summary.split("\n"):
        text_object.textLine(line)
    c.drawText(text_object)

    # Calculate Y after summary text
    summary_lines = summary.count("\n") + 1
    y_after_summary = summary_top - 18 - (summary_lines * 14) - 20
    if y_after_summary < 200:
        c.showPage()
        y_after_summary = height - 100

    # ─── “Survey” Section ───────────────────────────────────────────────────────────
    survey_header_y = y_after_summary
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, survey_header_y, "Survey Responses:")

    # Table column widths (point units)
    col1_x = 40
    col2_x = 300
    col3_x = 370
    line_height = 16
    y = survey_header_y - 20

    # Draw each question, selected answer, and comment
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

    for key, question_text in survey_questions.items():
        answer, comment = survey_responses.get(key, ("N/A", ""))
        # Draw question text (col1)
        c.setFont("Helvetica", 11)
        c.setFillColor(colors.black)
        c.drawString(col1_x, y, question_text)
        # Draw the chosen answer (col2)
        c.drawString(col2_x, y, f"▶  {answer}")
        # Draw the comment (col3), if any
        if comment.strip():
            c.setFont("Helvetica-Oblique", 10)
            c.setFillColor(colors.darkgray)
            c.drawString(col3_x, y, f"Comment: {comment}")

        y -= line_height
        if y < 150:
            c.showPage()
            y = height - 80

    # ─── “Site Photos” Section ───────────────────────────────────────────────────────
    if y < 200:
        c.showPage()
        y = height - 80

    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.black)
    c.drawString(40, y, "Site Photos:")
    y -= 20

    def draw_images_batch(start_x, start_y, files):
        """
        Helper to place up to 4 images side-by-side (scaled to width=150 pts).
        Returns the next available Y position.
        """
        x = start_x
        max_h = 0
        for uploaded in files or []:
            try:
                img = ImageReader(uploaded)
                iw, ih = img.getSize()
                scale = 150.0 / float(iw)
                scaled_w = 150
                scaled_h = ih * scale

                # If exceeding right margin, wrap to next line
                if x + scaled_w > width - 40:
                    x = start_x
                    start_y -= (max_h + 20)
                    max_h = 0

                c.drawImage(img, x, start_y - scaled_h, width=scaled_w, height=scaled_h)
                x += scaled_w + 20
                max_h = max(max_h, scaled_h)
            except Exception:
                continue

        return start_y - max_h - 20

    y = draw_images_batch(40, y, image_files_batch1)
    if image_files_batch2:
        if y < 80:
            c.showPage()
            y = height - 80
        y = draw_images_batch(40, y, image_files_batch2)

    # Finish up
    c.save()
    with open(tmp_path, "rb") as f:
        data = f.read()
    os.remove(tmp_path)
    return data


# ────────────────────────────────────────────────────────────────────────────────
# 4) Streamlit App Interface
# ────────────────────────────────────────────────────────────────────────────────

st.title("Site Visit Report 📋")

# 4.a) Project Title & Info Inputs
project_title = st.text_input(
    "Project Title",
    value="REUSE PIPELINE EXTENSION TO WINROCK",
    help="E.g. REUSE PIPELINE EXTENSION TO WINROCK",
)
site_address = st.text_input(
    "Site Address / Location",
    value="Constitution Ave NE, Albuquerque, NM 87110",
)
job_number = st.text_input(
    "Job #",
    value="2302.012",
    help="Your internal Job Number or Project ID",
)
prepared_by = st.text_input(
    "Prepared By",
    value="Arlee Engineer",
    help="Name of person preparing this report",
)

# 4.b) Brief Summary
st.markdown("---")
st.subheader("Brief Summary")
summary = st.text_area(
    "Describe what you saw/did on site (use Enter for new lines)",
    height=120,
)

# 4.c) Survey Section
st.markdown("---")
st.subheader("Survey")

survey_questions = [
    "1) Did weather cause any delays?",
    "2) Any instruction Contractor and Contractor’s actions?",
    "3) Any general comments or unusual events?",
    "4) Any schedule delays occur?",
    "5) Materials on site?",
    "6) Contractor and Subcontractor Equipment onsite?",
    "7) Testing?",
    "8) Any visitors on site?",
    "9) Any accidents on site today?",
]

survey_answers = {}
for idx, qtext in enumerate(survey_questions, start=1):
    q_key = f"Q{idx}"
    comm_key = f"{q_key}_comment"

    # layout with 3 columns: Question / Radio / Comment
    col1, col2, col3 = st.columns([4, 2, 6])
    with col1:
        st.write(f"**{qtext}**")
    with col2:
        choice = st.radio(
            label="",
            options=("N/A", "No", "Yes"),
            index=0,
            key=q_key,
            horizontal=True,
        )
    with col3:
        comment = st.text_input(
            label="",
            placeholder="Optional comment…",
            key=comm_key,
        )
    survey_answers[q_key] = (choice, comment)

# 4.d) Image Upload (two batches, up to 4 each)
st.markdown("---")
st.subheader("Site Photos")

image_files_batch1 = st.file_uploader(
    "Upload images (batch 1 of 2, up to 4 pics)",
    type=["png", "jpg", "jpeg"],
    accept_multiple_files=True,
    key="batch1",
)
if image_files_batch1 and len(image_files_batch1) > 4:
    st.warning("Please only upload up to 4 images in batch 1.")
    image_files_batch1 = image_files_batch1[:4]

image_files_batch2 = st.file_uploader(
    "Upload images (batch 2 of 2, up to 4 pics)",
    type=["png", "jpg", "jpeg"],
    accept_multiple_files=True,
    key="batch2",
)
if image_files_batch2 and len(image_files_batch2) > 4:
    st.warning("Please only upload up to 4 images in batch 2.")
    image_files_batch2 = image_files_batch2[:4]

# 4.e) Show live ABQ time + temperature
st.markdown("---")
abq_tz = ZoneInfo("America/Denver")
now_abq_display = datetime.now(abq_tz).strftime("%Y-%m-%d %H:%M:%S")
temp_display = get_current_temperature_abq()
st.write(f"**Current Time (ABQ):** {now_abq_display}")
if temp_display != "N/A":
    st.write(f"**Current Temperature (°F):** {temp_display}")
else:
    st.info("Unable to fetch temperature for ABQ. It will show as “N/A” in the PDF.")

# 4.f) Generate & Download Button
st.markdown("---")
if st.button("Generate PDF"):
    missing_fields = []
    if not project_title.strip():
        missing_fields.append("• Project Title")
    if not site_address.strip():
        missing_fields.append("• Site Address")
    if not job_number.strip():
        missing_fields.append("• Job #")
    if not prepared_by.strip():
        missing_fields.append("• Prepared By")
    if not summary.strip():
        missing_fields.append("• Brief Summary")

    if missing_fields:
        st.error("Please fill in the following:\n" + "\n".join(missing_fields))
    else:
        try:
            with st.spinner("Creating PDF…"):
                pdf_bytes = generate_pdf(
                    project_title=project_title,
                    site_address=site_address,
                    job_number=job_number,
                    prepared_by=prepared_by,
                    summary=summary,
                    survey_responses=survey_answers,
                    image_files_batch1=image_files_batch1,
                    image_files_batch2=image_files_batch2,
                )
        except Exception as e:
            st.error(f"🚨 Error generating PDF:\n{e}")
        else:
            timestamp = datetime.now(abq_tz).strftime("%Y%m%d_%H%M%S")
            filename = f"site_visit_report_{timestamp}.pdf"
            st.success("✅ PDF created!")
            st.download_button(
                label="Download PDF",
                data=pdf_bytes,
                file_name=filename,
                mime="application/pdf",
            )
