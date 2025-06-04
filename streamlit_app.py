# streamlit_app.py

import os
import tempfile
import requests
from datetime import datetime, date

import streamlit as st
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

#
# ────────────────────────────────────────────────────────────────────── START PAGE SETUP ─────
#
st.set_page_config(page_title="Site Visit Report", layout="centered")
st.title("Site Visit Report 📋")

#
# ────────────────────────────────────────────────────────────────────── FETCH CURRENT TIME & TEMP ─────
#
# 1) Current server time
now = datetime.now()
current_time_str = now.strftime("%Y-%m-%d %H:%M:%S")

# 2) Fetch Albuquerque, NM temperature from OpenWeatherMap
#    You must set OWM_API_KEY in Streamlit secrets (under Settings → Secrets).
owm_key = st.secrets.get("OWM_API_KEY", None)

def fetch_abq_temperature(api_key: str) -> str:
    """
    Calls OpenWeatherMap One Call API for Albuquerque, NM (lat=35.0853, lon=-106.6056).
    Returns a string like "64°F" or "N/A" if something went wrong.
    """
    if not api_key:
        return "N/A"
    try:
        # Albuquerque coordinates
        lat, lon = 35.0853, -106.6056
        url = (
            f"https://api.openweathermap.org/data/2.5/onecall?"
            f"lat={lat}&lon={lon}&units=imperial&appid={api_key}"
        )
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        temp_f = data["current"]["temp"]  # in Fahrenheit
        return f"{round(temp_f)}°F"
    except Exception:
        return "N/A"

current_temp_str = fetch_abq_temperature(owm_key)

# Display at top
st.markdown(
    f"""
    <div style="background-color:#006e8e; color:white; padding:10px; border-radius:4px;">
        <strong>Current Time:</strong> {current_time_str} &nbsp;|&nbsp;
        <strong>Current Temp (ABQ, NM):</strong> {current_temp_str}
    </div>
    """,
    unsafe_allow_html=True,
)
st.write("")  # small spacing


#
# ────────────────────────────────────────────────────────────────────── USER INPUTS ─────
#
with st.form(key="site_visit_form"):
    # Project Title (free‐text)
    project_title = st.text_input("Project Title", max_chars=80)

    # Site Address / Location
    site_address = st.text_input("Site Address / Location", max_chars=120)

    # Date of Visit (defaults to today)
    visit_date = st.date_input("Date of Visit", value=date.today())

    st.markdown("---")
    st.subheader("Brief Summary")
    summary = st.text_area("Describe what you saw / did on site", height=120)

    st.markdown("---")
    st.subheader("Survey")

    # For each question, we show: Question text, N/A/No/Yes radio, + a comment box to the right.
    def question_with_comment(label: str, key_base: str):
        cols = st.columns([1, 1])
        with cols[0]:
            choice = st.radio(
                label,
                ("N/A", "No", "Yes"),
                index=0,
                key=f"{key_base}_choice",
                horizontal=True,
            )
        with cols[1]:
            comment = st.text_input(
                f"Comments for: {label}",
                key=f"{key_base}_comment",
            )
        return choice, comment

    q1, q1_comment = question_with_comment("1. Did weather cause any delays?", "q1")
    q2, q2_comment = question_with_comment(
        "2. Any instruction Contractor and Contractor’s actions?", "q2"
    )
    q3, q3_comment = question_with_comment(
        "3. Any general comments or unusual events?", "q3"
    )
    q4, q4_comment = question_with_comment("4. Any schedule delays occur?", "q4")
    q5, q5_comment = question_with_comment("5. Materials on site?", "q5")
    q6, q6_comment = question_with_comment(
        "6. Contractor and Subcontractor Equipment onsite?", "q6"
    )
    q7, q7_comment = question_with_comment("7. Testing?", "q7")
    q8, q8_comment = question_with_comment("8. Any visitors on site?", "q8")
    q9, q9_comment = question_with_comment("9. Any accidents on site today?", "q9")

    st.markdown("---")
    st.subheader("Upload Images (up to 8 pics total)")

    # Two separate uploaders: batch1 and batch2, each up to 4 images
    uploaded_batch1 = st.file_uploader(
        "Upload images (batch 1 of 2, up to 4 pics)",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="images1",
    )
    if len(uploaded_batch1 or []) > 4:
        st.warning("Please upload at most 4 images in batch 1.")
        uploaded_batch1 = uploaded_batch1[:4]

    uploaded_batch2 = st.file_uploader(
        "Upload images (batch 2 of 2, up to 4 pics)",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="images2",
    )
    if len(uploaded_batch2 or []) > 4:
        st.warning("Please upload at most 4 images in batch 2.")
        uploaded_batch2 = uploaded_batch2[:4]

    submitted = st.form_submit_button(label="Generate PDF")

#
# ────────────────────────────────────────────────────────────────────── PDF GENERATION ─────
#
def generate_pdf_bytes(
    project_title: str,
    site_address: str,
    visit_date: date,
    summary: str,
    survey_answers: dict,
    survey_comments: dict,
    image_files: list,
) -> bytes:
    """
    Construct a PDF (in memory) using ReportLab. Returns raw PDF bytes.
    """
    # 1) Create a temporary file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.close()
    pdf_path = tmp.name

    c = canvas.Canvas(pdf_path, pagesize=letter)
    w, h = letter  # width, height in points

    # ── Header ──────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, h - 50, "Site Visit Report")

    c.setFont("Helvetica", 12)
    c.drawString(50, h - 80, f"Project: {project_title}")
    c.drawString(50, h - 100, f"Location: {site_address}")
    c.drawString(350, h - 80, f"Date of Visit: {visit_date.strftime('%Y-%m-%d')}")

    # ── Brief Summary Box ───────────────────────────────────
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, h - 140, "Brief Summary:")
    text = c.beginText(50, h - 160)
    text.setFont("Helvetica", 12)
    for line in summary.split("\n"):
        text.textLine(line)
    c.drawText(text)

    # ── Survey ──────────────────────────────────────────────
    survey_top = h - 300
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, survey_top, "Survey:")

    # Each question + answer + comment
    line_y = survey_top - 20
    c.setFont("Helvetica", 12)
    for i in range(1, 10):
        q_text = survey_answers[f"q{i}_text"]
        ans = survey_answers[f"q{i}_ans"]
        comm = survey_comments[f"q{i}_comm"]

        # Draw the question number + text
        c.drawString(50, line_y, q_text)

        # Draw the answer text
        c.drawString(350, line_y, f"Answer: {ans}")

        # Draw the comment (if any)
        if comm:
            c.setFont("Helvetica-Oblique", 11)
            c.drawString(450, line_y, f"Comment: {comm}")
            c.setFont("Helvetica", 12)

        line_y -= 20

    # ── Images ──────────────────────────────────────────────
    if image_files:
        # reserve a portion of the lower page for images
        y_pos = line_y - 20
        max_width = 100
        max_height = 75
        x_pos = 50

        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y_pos, "Photos:")
        y_pos -= 15

        for img_file in image_files:
            try:
                img_data = img_file.read()
                img_reader = canvas.ImageReader(img_data)
                iw, ih = img_reader.getSize()

                scale = min(max_width / iw, max_height / ih)
                draw_w, draw_h = iw * scale, ih * scale

                c.drawImage(
                    img_reader,
                    x_pos,
                    y_pos - draw_h,
                    width=draw_w,
                    height=draw_h,
                )
                x_pos += draw_w + 10
                if x_pos + max_width > w - 50:
                    x_pos = 50
                    y_pos -= max_height + 10
            except Exception:
                continue

    c.showPage()
    c.save()

    # Read the file’s bytes and delete it
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    os.remove(pdf_path)
    return pdf_bytes


if submitted:
    # Collect survey answers and comments in dictionaries
    survey_answers = {}
    survey_comments = {}
    for i, q in enumerate(
        [
            "1. Did weather cause any delays?",
            "2. Any instruction Contractor and Contractor’s actions?",
            "3. Any general comments or unusual events?",
            "4. Any schedule delays occur?",
            "5. Materials on site?",
            "6. Contractor and Subcontractor Equipment onsite?",
            "7. Testing?",
            "8. Any visitors on site?",
            "9. Any accidents on site today?",
        ],
        start=1,
    ):
        survey_answers[f"q{i}_text"] = q
        survey_answers[f"q{i}_ans"] = st.session_state.get(f"q{i}_choice", "N/A")
        survey_comments[f"q{i}_comm"] = st.session_state.get(f"q{i}_comment", "")

    # Combine images from both batches
    all_images = []
    if uploaded_batch1:
        all_images.extend(uploaded_batch1)
    if uploaded_batch2:
        all_images.extend(uploaded_batch2)

    # Generate PDF bytes
    try:
        pdf_bytes = generate_pdf_bytes(
            project_title=project_title,
            site_address=site_address,
            visit_date=visit_date,
            summary=summary,
            survey_answers=survey_answers,
            survey_comments=survey_comments,
            image_files=all_images,
        )
        st.success("PDF generated successfully!")
        st.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name=f"SiteVisit_{visit_date.strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
        )
    except Exception as e:
        st.error(f"Error generating PDF: {e}")
