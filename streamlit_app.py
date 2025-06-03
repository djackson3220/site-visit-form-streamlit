import os
import tempfile
import smtplib
from email.message import EmailMessage
from datetime import date

import streamlit as st
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# ─────────────────────────────────────────────────────────────────────────────
# 1) Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Site Visit Report", layout="centered")

# ─────────────────────────────────────────────────────────────────────────────
# 2) Helper: generate PDF with embedded images and full survey
# ─────────────────────────────────────────────────────────────────────────────
def generate_pdf(visitor, visit_date, summary, survey_responses, image_files):
    """
    - visitor: str
    - visit_date: str (YYYY-MM-DD)
    - summary: str (multi‐line)
    - survey_responses: dict where each key is a question string, and each value is a tuple:
         (choice_str, description_str)
       e.g. { "Did weather cause any delays?": ("Yes", "Heavy rain in morning"), ... }
    - image_files: list of in‐memory file‐like objects for images (up to 8)
    """
    # Create a temporary file for the PDF
    tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    c = canvas.Canvas(tmp_pdf.name, pagesize=letter)
    width, height = letter

    # ─── Header ───────────────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, "Site Visit Report")

    # ─── Visitor Info ─────────────────────────────────────────────────────────
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 80, f"Visitor: {visitor}")
    c.drawString(300, height - 80, f"Date: {visit_date}")

    # ─── Survey Section ───────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 110, "Survey:")
    y = height - 130
    c.setFont("Helvetica", 12)

    for question, (choice, desc) in survey_responses.items():
        # Draw the question and the choice
        c.drawString(60, y, f"- {question} [{choice}]")
        y -= 18
        # If there is a non‐empty description, draw it in smaller text
        if desc.strip() != "":
            c.setFont("Helvetica-Oblique", 10)
            c.drawString(72, y, f"  • {desc}")
            c.setFont("Helvetica", 12)
            y -= 14
        # Check if we’re too low on the page and need a new page
        if y < 120:
            c.showPage()
            y = height - 50
            c.setFont("Helvetica-Bold", 14)
            c.drawString(50, y, "Survey (cont’d):")
            c.setFont("Helvetica", 12)
            y -= 20

    # ─── Brief Summary ─────────────────────────────────────────────────────────
    # Leave some space below survey
    if y < 200:
        c.showPage()
        y = height - 50

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "Brief Summary:")
    y -= 20
    c.setFont("Helvetica", 12)

    for line in summary.split("\n"):
        c.drawString(60, y, line)
        y -= 16
        if y < 120:
            c.showPage()
            y = height - 50
            c.setFont("Helvetica", 12)

    # ─── Images ────────────────────────────────────────────────────────────────
    # Place each image at most 2 per row, scaled to max width=200 (maintaining aspect)
    # Start below summary if space; else new page
    if y < 300:
        c.showPage()
        y = height - 50

    x_offset = 50
    img_max_w = 200
    gap = 20
    count = 0
    for img_bytes in image_files:
        try:
            img = ImageReader(img_bytes)
            iw, ih = img.getSize()
            aspect = ih / iw
            img_w = img_max_w
            img_h = img_max_w * aspect

            # If no room vertically, make new page
            if y - img_h < 50:
                c.showPage()
                y = height - 50
                x_offset = 50
                count = 0

            c.drawImage(img, x_offset, y - img_h, width=img_w, height=img_h)

            # Move right for next image
            if count % 2 == 0:
                x_offset += img_max_w + gap
            else:
                # Two images placed → move down to new row
                x_offset = 50
                y -= img_h + gap

            count += 1

        except Exception:
            # Skip invalid images
            continue

    c.showPage()
    c.save()
    return tmp_pdf.name  # Path to the generated PDF file


# ─────────────────────────────────────────────────────────────────────────────
# 3) Helper: send email with attachment (Office365 SMTP)
# ─────────────────────────────────────────────────────────────────────────────
def send_email(recipient, visitor, visit_date, pdf_path, video_paths=None):
    """
    Emails the PDF at pdf_path to the recipient. (video_paths is unused since we no longer attach videos.)
    """
    EMAIL_USER = os.getenv("STREAMLIT_EMAIL_USER")
    EMAIL_PASS = os.getenv("STREAMLIT_EMAIL_PASS")

    msg = EmailMessage()
    msg["Subject"] = f"Site Visit Report from {visitor}"
    msg["From"] = EMAIL_USER
    msg["To"] = recipient
    msg.set_content(
        f"Hello,\n\n"
        f"Attached is the site visit report (PDF) by {visitor} on {visit_date}.\n\n"
        f"Regards,\n{visitor}"
    )

    # Attach the PDF
    with open(pdf_path, "rb") as f:
        data = f.read()
    msg.add_attachment(
        data,
        maintype="application",
        subtype="pdf",
        filename=f"site_visit_{visitor}_{visit_date}.pdf"
    )

    # Send via SMTP (Office365)
    with smtplib.SMTP("smtp.office365.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)


# ─────────────────────────────────────────────────────────────────────────────
# 4) Streamlit UI
# ─────────────────────────────────────────────────────────────────────────────
st.title("Site Visit Report 📝")

# — Basic fields —
visitor_name = st.text_input("Your Name", max_chars=50)
visit_date = st.date_input("Date of Visit", value=date.today())
summary = st.text_area("Brief Summary", help="Describe what you saw/did on site", height=120)

# ─────────────────────────────────────────────────────────────────────────────
#  Survey Questions (all 9)
# ─────────────────────────────────────────────────────────────────────────────
# For each question, we use a three‐option radio: ["N/A", "No", "Yes"].
# If the user selects "No" or "Yes", a description box appears.

survey_responses = {}

# 1. Did weather cause any delays?
choice1 = st.radio("1. Did weather cause any delays?", ("N/A", "No", "Yes"), index=0, horizontal=True)
desc1 = ""
if choice1 in ("No", "Yes"):
    desc1 = st.text_input("Description (weather delays)", "")
survey_responses["Did weather cause any delays?"] = (choice1, desc1)

# 2. Any instruction Contractor and Contractor’s actions?
choice2 = st.radio("2. Any instruction Contractor and Contractor’s actions?", ("N/A", "No", "Yes"), index=0, horizontal=True)
desc2 = ""
if choice2 in ("No", "Yes"):
    desc2 = st.text_input("Description (contractor actions)", "")
survey_responses["Any instruction Contractor and Contractor’s actions?"] = (choice2, desc2)

# 3. Any general comments or unusual events?
choice3 = st.radio("3. Any general comments or unusual events?", ("N/A", "No", "Yes"), index=0, horizontal=True)
desc3 = ""
if choice3 in ("No", "Yes"):
    desc3 = st.text_input("Description (unusual events)", "")
survey_responses["Any general comments or unusual events?"] = (choice3, desc3)

# 4. Any schedule delays occur?
choice4 = st.radio("4. Any schedule delays occur?", ("N/A", "No", "Yes"), index=0, horizontal=True)
desc4 = ""
if choice4 in ("No", "Yes"):
    desc4 = st.text_input("Description (schedule delays)", "")
survey_responses["Any schedule delays occur?"] = (choice4, desc4)

# 5. Materials on site?
choice5 = st.radio("5. Materials on site?", ("N/A", "No", "Yes"), index=0, horizontal=Tru
