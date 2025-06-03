import os
import tempfile
import time
from datetime import datetime
import requests

import streamlit as st
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# ─── 1) Page config ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Site Visit Report",
    layout="centered",
)

# ─── 2) Helper: fetch current temperature for Albuquerque, NM ────────────────────

def get_current_temperature(api_key: str) -> str:
    """
    Uses OpenWeatherMap's API to fetch the current temperature in Albuquerque, NM.
    Returns the temperature in Fahrenheit as a string, or "N/A" if something goes wrong.
    """
    try:
        # OpenWeatherMap endpoint for current weather by city name:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": "Albuquerque,US",
            "units": "imperial",   # "imperial" returns °F
            "appid": api_key,
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if response.status_code == 200 and "main" in data:
            temp_f = data["main"]["temp"]
            return f"{temp_f:.1f}"
        else:
            return "N/A"
    except Exception:
        return "N/A"


# ─── 3) Helper: generate PDF with embedded survey data + images ─────────────────

def generate_pdf(
    visitor: str,
    visit_date: str,
    site_address: str,
    summary: str,
    survey_answers: dict,
    image_files_batch1,
    image_files_batch2,
    api_key: str,
) -> bytes:
    """
    Creates a PDF in memory (BytesIO) containing:
      - Current date/time
      - Current temperature in Albuquerque
      - Visitor name
      - Visit date
      - Site address
      - Brief summary
      - Survey answers (checkbox/radio results)
      - Up to 8 images (4 in batch1, 4 in batch2), each scaled to max width of 200 px
    Returns the raw PDF bytes.
    """
    # 1) First, fetch time + temperature:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    temp_str = get_current_temperature(api_key)

    # 2) Create a temporary file (BytesIO) so ReportLab can write into it:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp_pdf_path = tmp.name
    tmp.close()

    c = canvas.Canvas(tmp_pdf_path, pagesize=letter)
    width, height = letter  # 612 x 792

    # ── Header: Title ────────────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 18)
    c.drawString(200, height - 50, "Site Visit Report")

    # ── Time & Temp ─────────────────────────────────────────────────────────────
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 80, f"Generated At     : {now}")
    c.drawString(50, height - 95, f"Temperature (°F): {temp_str}")

    # ── Divider ───────────────────────────────────────────────────────────────────
    c.line(50, height - 105, width - 50, height - 105)

    # ── Visitor + Visit Date + Address ───────────────────────────────────────────
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 125, f"Visitor Name      :")
    c.setFont("Helvetica", 12)
    c.drawString(200, height - 125, visitor)

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 145, f"Date of Visit     :")
    c.setFont("Helvetica", 12)
    c.drawString(200, height - 145, visit_date)

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 165, f"Site Address      :")
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

    # Compute where to start the survey section, based on how many summary lines:
    summary_lines = summary.count("\n") + 1
    survey_y_start = height - 215 - (summary_lines * 12) - 20

    # ── Survey ────────────────────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, survey_y_start, "Survey Responses:")

    c.setFont("Helvetica", 11)
    line_height = 14
    y = survey_y_start - 20

    # The survey questions are keyed in survey_answers as: {"Q1": "N/A"/"No"/"Yes", ...}
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
        answer = survey_answers.get(key, "N/A")
        c.drawString(60, y, f"{question}   ▶ {answer}")
        y -= line_height

    # ── Images ─────────────────────────────────────────────────────────────────────
    # Start a new page if needed:
    if y < 200:
        c.showPage()
        y = height - 100

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Site Photos:")
    y -= 20

    def draw_images_at(start_x, start_y, files):
        """
        Draw up to 4 images in a row, each scaled to max width=200px (keeping aspect ratio).
        Returns the next y coordinate below the images.
        """
        x = start_x
        max_height_in_row = 0

        for uploaded_file in files:
            try:
                # Read the image into a PIL‐style object:
                img = ImageReader(uploaded_file)
                iw, ih = img.getSize()

                # Scale logic: max width=200, maintain aspect ratio
                scale = 200.0 / float(iw)
                scaled_w = 200
                scaled_h = ih * scale

                # If scaling would push us off the bottom, start a new row:
                if x + scaled_w > width - 50:
                    # Move to next row
                    x = start_x
                    start_y -= (max_height_in_row + 20)
                    max_height_in_row = 0

                c.drawImage(img, x, start_y - scaled_h, width=scaled_w, height=scaled_h)
                x += scaled_w + 20
                max_height_in_row = max(max_height_in_row, scaled_h)

            except Exception:
                # If an image fails, just skip it
                continue

        # Return the y coordinate after drawing all images
        return start_y - max_height_in_row - 20

    # First batch of up to 4 images
    y = draw_images_at(50, y, image_files_batch1 or [])

    # Second batch of up to 4 images (if space runs out, ReportLab will start a new page)
    if image_files_batch2:
        if y < 100:
            c.showPage()
            y = height - 100
        y = draw_images_at(50, y, image_files_batch2)

    # ── Finalize PDF ───────────────────────────────────────────────────────────────
    c.save()

    # Read the entire PDF from disk into memory as bytes, then delete the temp file
    with open(tmp_pdf_path, "rb") as f:
        pdf_bytes = f.read()
    os.remove(tmp_pdf_path)

    return pdf_bytes


# ─── 4) Streamlit UI ────────────────────────────────────────────────────────────

# Title + (optional) icon
st.title("Site Visit Report 📋")

# Show current time + temperature at the very top:
now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
# (We’ll fetch temp again inside generate_pdf, but you can show “N/A” here if you like)
st.write(f"**Current Time:** {now}")

# Briefly let the user know temperature will appear in the PDF
st.info("The PDF will include today’s temperature in Albuquerque, NM.")

# 4.a) Basic form inputs
visitor_name      = st.text_input("Your Name", max_chars=50)
visit_date        = st.date_input("Date of Visit", value=datetime.today())
site_address      = st.text_input("Site Address / Location", max_chars=100)
summary           = st.text_area(
    "Brief Summary",
    help="Describe what you saw/did on site. (Hit Enter for new lines.)",
    height=120,
)

# 4.b) Survey questions (radio buttons)
st.markdown("---")
st.header("Survey")
survey_answers = {}
survey_answers["Q1"] = st.radio("1) Did weather cause any delays?", ("N/A","No","Yes"), index=0, horizontal=True)
survey_answers["Q2"] = st.radio("2) Any instruction Contractor and Contractor’s actions?", ("N/A","No","Yes"), index=0, horizontal=True)
survey_answers["Q3"] = st.radio("3) Any general comments or unusual events?", ("N/A","No","Yes"), index=0, horizontal=True)
survey_answers["Q4"] = st.radio("4) Any schedule delays occur?", ("N/A","No","Yes"), index=0, horizontal=True)
survey_answers["Q5"] = st.radio("5) Materials on site?", ("N/A","No","Yes"), index=0, horizontal=True)
survey_answers["Q6"] = st.radio("6) Contractor and Subcontractor Equipment onsite?", ("N/A","No","Yes"), index=0, horizontal=True)
survey_answers["Q7"] = st.radio("7) Testing?", ("N/A","No","Yes"), index=0, horizontal=True)
survey_answers["Q8"] = st.radio("8) Any visitors on site?", ("N/A","No","Yes"), index=0, horizontal=True)
survey_answers["Q9"] = st.radio("9) Any accidents on site today?", ("N/A","No","Yes"), index=0, horizontal=True)

# 4.c) Image uploads (two separate batches of up to 4 each)
st.markdown("---")
st.header("Site Photos")

image_files_batch1 = st.file_uploader(
    "Upload images (batch 1 of 2, up to 4 pics)",
    type=["png","jpg","jpeg"],
    accept_multiple_files=True,
    key="batch1",
)
if image_files_batch1 and len(image_files_batch1) > 4:
    st.warning("Please only upload up to 4 images in this batch.")
    image_files_batch1 = image_files_batch1[:4]

image_files_batch2 = st.file_uploader(
    "Upload images (batch 2 of 2, up to 4 pics)",
    type=["png","jpg","jpeg"],
    accept_multiple_files=True,
    key="batch2",
)
if image_files_batch2 and len(image_files_batch2) > 4:
    st.warning("Please only upload up to 4 images in this batch.")
    image_files_batch2 = image_files_batch2[:4]

# 4.d) Ask for OpenWeatherMap API key in order to fetch temperature
st.markdown("---")
st.info(
    "To include the live temperature in Albuquerque, NM, enter your OpenWeatherMap API key below. "
    "If you leave it blank, the PDF will show “N/A.”"
)
owm_api_key = st.text_input(
    "OpenWeatherMap API Key",
    type="password",
    help="Sign up at https://openweathermap.org/ to get a free API key."
)

# 4.e) Generate & Download PDF button
st.markdown("---")
generate_pdf_button = st.button("Generate PDF")

if generate_pdf_button:
    # 5) Validation: ensure required fields are filled
    missing = []
    if not visitor_name.strip():
        missing.append("– Visitor Name is required.")
    if not site_address.strip():
        missing.append("– Site Address is required.")
    if not summary.strip():
        missing.append("– Brief Summary is required.")
    if missing:
        st.error("Please fill in the following fields before generating the PDF:\n" + "\n".join(missing))
    else:
        # 6) Build and download the PDF
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

        # 7) Offer it as a download
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"site_visit_report_{timestamp}.pdf"
        st.success("PDF generated successfully!")
        st.download_button(
            label="Download PDF",
            data=pdf_bytes,
            file_name=default_filename,
            mime="application/pdf",
        )
