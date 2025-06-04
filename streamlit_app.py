import os
import tempfile
import requests
from datetime import datetime, date

import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# ────────────────────────────────────────────────────────────────────────────────
# 1) PAGE CONFIGURATION
# ────────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Site Visit Report", layout="centered")

# ────────────────────────────────────────────────────────────────────────────────
# 2) WEATHER & TIME FETCHING (Albuquerque, NM)
# ────────────────────────────────────────────────────────────────────────────────

# Coordinates for Albuquerque, NM
LATITUDE = 35.0844
LONGITUDE = -106.6504

def fetch_current_temperature(lat: float, lon: float) -> float | None:
    """
    Queries Open-Meteo's "current_weather" endpoint for the given latitude/longitude.
    Returns the temperature in Fahrenheit (°F), or None on failure.
    """
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}&current_weather=true&temperature_unit=fahrenheit"
        )
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        data = r.json()
        return data.get("current_weather", {}).get("temperature")
    except Exception:
        return None

# Get current local time (server time ≈ ABQ time for our purposes)
current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Attempt to fetch the current temperature (°F)
current_temp = fetch_current_temperature(LATITUDE, LONGITUDE)
if current_temp is None:
    temp_display = "–"
else:
    temp_display = f"{round(current_temp)}°F"

# ────────────────────────────────────────────────────────────────────────────────
# 3) PDF GENERATION FUNCTION
# ────────────────────────────────────────────────────────────────────────────────

def generate_pdf(
    project_title: str,
    site_address: str,
    visit_date: str,
    prepared_by: str,
    summary: str,
    survey_responses: dict,
    image_files_batch1,
    image_files_batch2,
    time_str: str,
    temp_str: str,
) -> bytes:
    """
    Creates a PDF with the following structure:
      • Top light-blue banner: project_title (white, large) / site_address (white, smaller)
      • Thin darker-blue stripe just below: "Current Time: … | Current Temp: …"
      • Black sub-banner: "Date of Visit: <visit_date>" on the left, "Prepared By: <prepared_by>" on the right
      • "Brief Summary" text block
      • "Survey Responses" table (question / chosen answer / optional comment)
      • Up to 8 images (two batches of up to 4 each), each scaled to 150 pt width
    """
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp_path = tmp.name
    tmp.close()

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

    # ─── Thin Darker-Blue Strip (Time & Temperature) ───────────────────────────────
    strip_height = 20
    c.setFillColorRGB(0.05, 0.45, 0.60)  # darker-blue
    c.rect(0, height - banner_height - strip_height, width, strip_height, fill=1, stroke=0)

    c.setFont("Helvetica", 10)
    c.setFillColor(colors.white)
    # Draw “Current Time” on left
    c.drawString(40, height - banner_height - strip_height + 5, f"Current Time: {time_str}")
    # Draw “Current Temperature” on right
    c.drawRightString(width - 40, height - banner_height - strip_height + 5, f"Current Temp: {temp_str}")

    # ─── Black Sub-Banner (Date of Visit / Prepared By) ───────────────────────────
    sub_banner_height = 30
    c.setFillColorRGB(0, 0, 0)  # black
    y_black = height - banner_height - strip_height - sub_banner_height
    c.rect(0, y_black, width, sub_banner_height, fill=1, stroke=0)

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.white)
    # Date of Visit on left
    c.drawString(40, y_black + 8, f"Date of Visit: {visit_date}")
    # Prepared By on right
    c.drawRightString(width - 40, y_black + 8, f"Prepared By: {prepared_by}")

    # ─── Brief Summary Section ────────────────────────────────────────────────────
    summary_top = y_black - 30
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.black)
    c.drawString(40, summary_top, "Brief Summary:")

    text_object = c.beginText(40, summary_top - 18)
    text_object.setFont("Helvetica", 11)
    for line in summary.split("\n"):
        text_object.textLine(line)
    c.drawText(text_object)

    # Calculate Y after summary
    summary_lines = summary.count("\n") + 1
    y_after_summary = summary_top - 18 - (summary_lines * 14) - 20
    if y_after_summary < 200:
        c.showPage()
        y_after_summary = height - 80

    # ─── Survey Section ──────────────────────────────────────────────────────────
    survey_header_y = y_after_summary
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, survey_header_y, "Survey Responses:")

    col1_x = 40
    col2_x = 300
    col3_x = 370
    line_height = 16
    y = survey_header_y - 20

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
        c.setFont("Helvetica", 11)
        c.setFillColor(colors.black)
        c.drawString(col1_x, y, question_text)

        c.drawString(col2_x, y, f"▶ {answer}")

        if comment.strip():
            c.setFont("Helvetica-Oblique", 10)
            c.setFillColor(colors.darkgray)
            c.drawString(col3_x, y, f"Comment: {comment}")

        y -= line_height
        if y < 150:
            c.showPage()
            y = height - 80

    # ─── Site Photos Section ─────────────────────────────────────────────────────
    if y < 200:
        c.showPage()
        y = height - 80

    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.black)
    c.drawString(40, y, "Site Photos:")
    y -= 20

    def draw_images_batch(start_x, start_y, files):
        """
        Draw up to 4 images (scaled to width=150), wrapping to the next row if needed.
        Returns new Y after drawing.
        """
        x = start_x
        max_h = 0
        for uploaded in files or []:
            try:
                img = ImageReader(uploaded)
                iw, ih = img.getSize()
                scale = 150.0 / float(iw)
                w_img = 150
                h_img = ih * scale

                if x + w_img > width - 40:
                    x = start_x
                    start_y -= (max_h + 20)
                    max_h = 0

                c.drawImage(img, x, start_y - h_img, width=w_img, height=h_img)
                x += w_img + 20
                max_h = max(max_h, h_img)
            except Exception:
                continue

        return start_y - max_h - 20

    # Draw first batch
    y = draw_images_batch(40, y, image_files_batch1)

    # Draw second batch if present
    if image_files_batch2:
        if y < 80:
            c.showPage()
            y = height - 80
        y = draw_images_batch(40, y, image_files_batch2)

    c.save()
    with open(tmp_path, "rb") as f:
        data = f.read()
    os.remove(tmp_path)
    return data


# ────────────────────────────────────────────────────────────────────────────────
# 4) STREAMLIT APP LAYOUT
# ────────────────────────────────────────────────────────────────────────────────

st.title("Site Visit Report 📋")

# 4.a) Display current time & temperature at top
st.markdown(
    f"""
    <div style="background-color:#077d99; color:white; padding:10px 20px; border-radius:4px;">
      <strong>Current Time:</strong> {current_time}  | <strong>Current Temp (ABQ, NM):</strong> {temp_display}
    </div>
    """,
    unsafe_allow_html=True,
)

# 4.b) Project Title, Site Address/Location, Date of Visit, Prepared By
project_title = st.text_input(
    "Project Title",
    value="REUSE PIPELINE EXTENSION TO WINROCK",
    help="E.g. REUSE PIPELINE EXTENSION TO WINROCK",
)
site_address = st.text_input(
    "Site Address / Location",
    value="Constitution Ave NE, Albuquerque, NM 87110",
)
visit_date = st.date_input(
    "Date of Visit",
    value=date.today(),
    help="Select the date you visited the site",
)
prepared_by = st.text_input(
    "Prepared By",
    value="Arlee Engineer",
    help="Name of person preparing this report",
)

# 4.c) Brief Summary
st.markdown("---")
st.subheader("Brief Summary")
summary = st.text_area(
    "Describe what you saw/did on site (use Enter for line breaks)",
    height=120,
)

# 4.d) Survey
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

# 4.e) Image Upload (Two Batches of up to 4 each)
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

# 4.f) Generate & Download PDF Button
st.markdown("---")
if st.button("Generate PDF"):
    missing = []
    if not project_title.strip():
        missing.append("• Project Title")
    if not site_address.strip():
        missing.append("• Site Address")
    if not prepared_by.strip():
        missing.append("• Prepared By")
    if not summary.strip():
        missing.append("• Brief Summary")

    if missing:
        st.error("Please fill in the following:\n" + "\n".join(missing))
    else:
        try:
            with st.spinner("Creating PDF…"):
                pdf_bytes = generate_pdf(
                    project_title=project_title,
                    site_address=site_address,
                    visit_date=visit_date.strftime("%Y-%m-%d"),
                    prepared_by=prepared_by,
                    summary=summary,
                    survey_responses=survey_answers,
                    image_files_batch1=image_files_batch1,
                    image_files_batch2=image_files_batch2,
                    time_str=current_time,
                    temp_str=temp_display,
                )
        except Exception as e:
            st.error(f"🚨 Error generating PDF:\n{e}")
        else:
            filename = f"site_visit_report_{visit_date.strftime('%Y%m%d')}.pdf"
            st.success("✅ PDF created!")
            st.download_button(
                label="Download PDF",
                data=pdf_bytes,
                file_name=filename,
                mime="application/pdf",
            )
