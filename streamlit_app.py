import os
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import streamlit as st
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# ────────────────────────────────────────────────────────────────────────────────
# 1) Page configuration
# ────────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Site Visit Report", layout="centered")


# ────────────────────────────────────────────────────────────────────────────────
# 2) Function to fetch current temperature for Albuquerque, NM
# ────────────────────────────────────────────────────────────────────────────────

def get_current_temperature(api_key: str) -> str:
    """
    Query OpenWeatherMap API for current temperature (°F) in Albuquerque, NM.
    Returns a one‐decimal string (e.g. "75.2") or "N/A" on any error.
    """
    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": "Albuquerque,US",
            "units": "imperial",
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
# 3) Function to generate PDF
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
    Creates a PDF containing:
      • Current Albuquerque time and temperature (°F)
      • Visitor info, site address, summary
      • Survey answers + comments
      • Up to 8 images (two batches of 4)
    Returns the PDF file as raw bytes.
    """
    # 3.a) Get ABQ time and temperature
    abq_tz = ZoneInfo("America/Denver")
    now_abq = datetime.now(abq_tz).strftime("%Y-%m-%d %H:%M:%S")
    temp_str = get_current_temperature(api_key) if api_key else "N/A"

    # 3.b) Create a temporary PDF
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp_pdf_path = tmp.name
    tmp.close()

    c = canvas.Canvas(tmp_pdf_path, pagesize=letter)
    width, height = letter

    # Header
    c.setFont("Helvetica-Bold", 18)
    c.drawString(200, height - 50, "Site Visit Report")

    # Timestamp & temperature
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 80, f"Generated At (ABQ): {now_abq}")
    c.drawString(50, height - 95, f"Temperature (°F): {temp_str}")

    # Divider line
    c.line(50, height - 105, width - 50, height - 105)

    # Visitor info
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 125, "Visitor Name    :")
    c.setFont("Helvetica", 12)
    c.drawString(200, height - 125, visitor)

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 145, "Date of Visit   :")
    c.setFont("Helvetica", 12)
    c.drawString(200, height - 145, visit_date)

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 165, "Site Address    :")
    c.setFont("Helvetica", 12)
    c.drawString(200, height - 165, site_address)

    # Divider line
    c.line(50, height - 175, width - 50, height - 175)

    # Brief summary
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 195, "Brief Summary:")
    text_obj = c.beginText(50, height - 215)
    text_obj.setFont("Helvetica", 11)
    for line in summary.split("\n"):
        text_obj.textLine(line)
    c.drawText(text_obj)

    # Calculate where to start survey based on summary length
    summary_lines = summary.count("\n") + 1
    survey_y_start = height - 215 - (summary_lines * 12) - 20
    if survey_y_start < 200:
        c.showPage()
        survey_y_start = height - 100

    # Survey responses
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, survey_y_start, "Survey Responses:")
    c.setFont("Helvetica", 11)
    y = survey_y_start - 20
    line_height = 14

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
        choice, comment_text = survey_responses.get(key, ("N/A", ""))
        # Print question + answer
        c.drawString(60, y, f"{question}   ▶ {choice}")
        y -= line_height

        # If comment exists, print on next line (indented)
        if comment_text.strip():
            c.setFont("Helvetica-Oblique", 10)
            c.drawString(80, y, f"Comment: {comment_text}")
            c.setFont("Helvetica", 11)
            y -= line_height

        if y < 100:
            c.showPage()
            y = height - 100
            c.setFont("Helvetica", 11)

    # Divider before photos (if needed)
    if y < 200:
        c.showPage()
        y = height - 100

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Site Photos:")
    y -= 20

    # Function to place up to 4 images per row, scaled to width=200
    def draw_images(start_x, start_y, files):
        x = start_x
        max_h = 0
        for uploaded in files or []:
            try:
                img = ImageReader(uploaded)
                iw, ih = img.getSize()
                scale = 200.0 / float(iw)
                scaled_w = 200
                scaled_h = ih * scale

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

    y = draw_images(50, y, image_files_batch1)
    if image_files_batch2:
        if y < 100:
            c.showPage()
            y = height - 100
        y = draw_images(50, y, image_files_batch2)

    c.save()
    with open(tmp_pdf_path, "rb") as f:
        pdf_bytes = f.read()
    os.remove(tmp_pdf_path)
    return pdf_bytes


# ────────────────────────────────────────────────────────────────────────────────
# 4) Streamlit App Layout
# ────────────────────────────────────────────────────────────────────────────────

st.title("Site Visit Report 📋")

# 4.a) Visitor info + summary
visitor_name = st.text_input("Your Name", max_chars=50)
visit_date   = st.date_input("Date of Visit", value=datetime.today())
site_address = st.text_input("Site Address / Location", max_chars=100)
summary      = st.text_area(
    "Brief Summary", help="Describe what you saw/did on site (use Enter to create new lines)", height=120
)

# 4.b) Survey with comment boxes
st.markdown("---")
st.header("Survey")

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
for idx, question in enumerate(survey_questions, start=1):
    q_key    = f"Q{idx}"
    comm_key = f"Q{idx}_comment"

    # Three columns: question text | radio buttons | comment box
    col_txt, col_rad, col_comm = st.columns([4, 2, 6])

    with col_txt:
        st.write(f"**{question}**")
    with col_rad:
        choice = st.radio(
            label="",
            options=("N/A", "No", "Yes"),
            index=0,
            key=q_key,
            horizontal=True,
        )
    with col_comm:
        comment = st.text_input(
            label="",
            placeholder="Optional comment…",
            key=comm_key,
        )

    survey_answers[q_key] = (choice, comment)

# 4.c) Photo upload (two batches of up to 4 each)
st.markdown("---")
st.header("Site Photos")

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

# 4.d) OpenWeatherMap API key (optional)
st.markdown("---")
st.info(
    "If you want the PDF to include current Albuquerque temperature, enter your OpenWeatherMap API key. "
    "Otherwise temperature will default to “N/A.”"
)
owm_api_key = st.text_input(
    "OpenWeatherMap API Key",
    type="password",
    help="Sign up at https://openweathermap.org/ to get a free key.",
)

# 4.e) Show live ABQ time + temperature on the form
abq_tz  = ZoneInfo("America/Denver")
now_abq = datetime.now(abq_tz).strftime("%Y-%m-%d %H:%M:%S")
st.write(f"**Current Time (ABQ):** {now_abq}")

if owm_api_key:
    temp_live = get_current_temperature(owm_api_key)
    if temp_live != "N/A":
        st.write(f"**Current Temperature (°F):** {temp_live}")
    else:
        st.info("Unable to fetch temperature. Verify your API key.")
else:
    st.info("No API key entered → temperature will show as “N/A” in PDF.")

# 4.f) Generate & download PDF
st.markdown("---")
if st.button("Generate PDF"):
    # Must have name, address, summary
    missing = []
    if not visitor_name.strip():
        missing.append("• Visitor Name is required.")
    if not site_address.strip():
        missing.append("• Site Address is required.")
    if not summary.strip():
        missing.append("• Brief Summary is required.")

    if missing:
        st.error("Please fill in:\n" + "\n".join(missing))
    else:
        try:
            with st.spinner("Creating PDF…"):
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
            st.error(f"🚨 Error generating PDF:\n\n{e}")
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
