import os
import tempfile
import smtplib
from email.message import EmailMessage
from datetime import date, datetime

import requests
import streamlit as st
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# ─────────────────────────────────────────────────────────────────────────────
# 1) Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Site Visit Report", layout="centered")

# ─────────────────────────────────────────────────────────────────────────────
# 2) Auto‐capture current time (server time) and approximate temperature (via IP)
# ─────────────────────────────────────────────────────────────────────────────
now = datetime.now()
current_time_str = now.strftime("%Y-%m-%d %H:%M:%S")  # e.g. "2025-06-03 14:22:10"
temperature_f = None

try:
    # 2A) Get approximate lat/lon from IP
    geo_resp = requests.get("https://ipapi.co/json/")
    geo_resp.raise_for_status()
    geo_data = geo_resp.json()
    lat = geo_data.get("latitude")
    lon = geo_data.get("longitude")

    if lat is not None and lon is not None:
        # 2B) Query Open-Meteo for current weather (temperature in Celsius)
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&current_weather=true"
        )
        weather_resp = requests.get(weather_url)
        weather_resp.raise_for_status()
        weather_data = weather_resp.json()
        temp_c = weather_data["current_weather"]["temperature"]
        temperature_f = temp_c * 9/5 + 32
        temperature_f = round(temperature_f, 1)
except Exception:
    # If any step fails (no internet, API down, etc.), we'll leave temperature_f = None
    temperature_f = None

# ─────────────────────────────────────────────────────────────────────────────
# 3) Helper: generate PDF with images, survey, address, time & temperature
# ─────────────────────────────────────────────────────────────────────────────
def generate_pdf(visitor, visit_date, address, current_time, temperature, summary, survey_responses, image_files):
    """
    - visitor: str
    - visit_date: str (YYYY-MM-DD)
    - address: str (manually entered)
    - current_time: str (YYYY-MM-DD HH:MM:SS)
    - temperature: float or None (in °F)
    - summary: str (multi‐line)
    - survey_responses: dict where each key is a question string, and each value is a tuple:
         (choice_str, description_str)
    - image_files: list of in‐memory file‐like objects for images (up to 8)
    """
    tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    c = canvas.Canvas(tmp_pdf.name, pagesize=letter)
    width, height = letter

    # ─── Header ───────────────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, "Site Visit Report")

    # ─── Visitor Info, Address, Time & Temperature ────────────────────────────
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 80, f"Visitor: {visitor}")
    c.drawString(300, height - 80, f"Date: {visit_date}")

    # If an address was provided:
    if address.strip():
        c.drawString(50, height - 100, f"Site Address: {address}")
        y_pos = height - 120
    else:
        y_pos = height - 100

    # Show current time
    c.drawString(50, y_pos, f"Time: {current_time}")
    y_pos -= 20

    # Show temperature if available
    if temperature is not None:
        c.drawString(50, y_pos, f"Temperature (°F): {temperature}")
        y_pos -= 20

    # ─── Survey Section ───────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y_pos, "Survey:")
    y_pos -= 20
    c.setFont("Helvetica", 12)
    for question, (choice, desc) in survey_responses.items():
        c.drawString(60, y_pos, f"- {question} [{choice}]")
        y_pos -= 18
        if desc.strip():
            c.setFont("Helvetica-Oblique", 10)
            c.drawString(72, y_pos, f"• {desc}")
            c.setFont("Helvetica", 12)
            y_pos -= 14
        if y_pos < 120:
            c.showPage()
            y_pos = height - 50
            c.setFont("Helvetica-Bold", 14)
            c.drawString(50, y_pos, "Survey (cont’d):")
            y_pos -= 20
            c.setFont("Helvetica", 12)

    # ─── Brief Summary ─────────────────────────────────────────────────────────
    if y_pos < 200:
        c.showPage()
        y_pos = height - 50

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y_pos, "Brief Summary:")
    y_pos -= 20
    c.setFont("Helvetica", 12)
    for line in summary.split("\n"):
        c.drawString(60, y_pos, line)
        y_pos -= 16
        if y_pos < 120:
            c.showPage()
            y_pos = height - 50
            c.setFont("Helvetica", 12)

    # ─── Images ────────────────────────────────────────────────────────────────
    if y_pos < 300:
        c.showPage()
        y_pos = height - 50

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

            if y_pos - img_h < 50:
                c.showPage()
                y_pos = height - 50
                x_offset = 50
                count = 0

            c.drawImage(img, x_offset, y_pos - img_h, width=img_w, height=img_h)

            if count % 2 == 0:
                x_offset += img_max_w + gap
            else:
                x_offset = 50
                y_pos -= img_h + gap

            count += 1

        except Exception:
            continue

    c.showPage()
    c.save()
    return tmp_pdf.name


# ─────────────────────────────────────────────────────────────────────────────
# 4) Helper: send email via Gmail SMTP (App Password)
# ─────────────────────────────────────────────────────────────────────────────
def send_email(recipient, visitor, visit_date, pdf_path):
    """
    Send the PDF via Gmail SMTP (using the App Password from Secrets).
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

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)


# ─────────────────────────────────────────────────────────────────────────────
# 5) Streamlit UI
# ─────────────────────────────────────────────────────────────────────────────
st.title("Site Visit Report 📝")

# — Show current time and temperature at top of form —
st.markdown(f"**Current Time:** {current_time_str}")
if temperature_f is not None:
    st.markdown(f"**Current Temperature (°F):** {temperature_f}")
else:
    st.markdown("**Current Temperature (°F):** Could not fetch")

st.write("---")

# — Basic fields —
visitor_name = st.text_input("Your Name", max_chars=50)
visit_date = st.date_input("Date of Visit", value=date.today())

# — Manual Site Address field —
address = st.text_input("Site Address / Location", "")

summary = st.text_area("Brief Summary", help="Describe what you saw/did on site", height=120)


# ─────────────────────────────────────────────────────────────────────────────
# 6) Survey Questions (all 9)
# ─────────────────────────────────────────────────────────────────────────────
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
choice5 = st.radio("5. Materials on site?", ("N/A", "No", "Yes"), index=0, horizontal=True)
desc5 = ""
if choice5 in ("No", "Yes"):
    desc5 = st.text_input("Description (materials)", "")
survey_responses["Materials on site?"] = (choice5, desc5)

# 6. Contractor and Subcontractor Equipment onsite?
choice6 = st.radio("6. Contractor and Subcontractor Equipment onsite?", ("N/A", "No", "Yes"), index=0, horizontal=True)
desc6 = ""
if choice6 in ("No", "Yes"):
    desc6 = st.text_input("Description (equipment on site)", "e.g., 4 work trucks, 1 water truck, 1-54k loader, …")
survey_responses["Contractor and Subcontractor Equipment onsite?"] = (choice6, desc6)

# 7. Testing?
choice7 = st.radio("7. Testing?", ("N/A", "No", "Yes"), index=0, horizontal=True)
desc7 = ""
if choice7 in ("No", "Yes"):
    desc7 = st.text_input("Description (testing)", "")
survey_responses["Testing?"] = (choice7, desc7)

# 8. Any visitors on site?
choice8 = st.radio("8. Any visitors on site?", ("N/A", "No", "Yes"), index=0, horizontal=True)
desc8 = ""
if choice8 in ("No", "Yes"):
    desc8 = st.text_input("Description (visitors)", "")
survey_responses["Any visitors on site?"] = (choice8, desc8)

# 9. Any accidents on site today?
choice9 = st.radio("9. Any accidents on site today?", ("N/A", "No", "Yes"), index=0, horizontal=True)
desc9 = ""
if choice9 in ("No", "Yes"):
    desc9 = st.text_input("Description (accidents)", "")
survey_responses["Any accidents on site today?"] = (choice9, desc9)


# ─────────────────────────────────────────────────────────────────────────────
# 7) File uploaders (two separate uploaders, each up to 4 images → total 8)
# ─────────────────────────────────────────────────────────────────────────────
st.write("---")

uploaded_batch1 = st.file_uploader(
    label="Upload images (batch 1 of 2, up to 4 pics)",
    type=["png", "jpg", "jpeg"],
    accept_multiple_files=True,
    key="batch1"
)
if len(uploaded_batch1) > 4:
    st.warning("Batch 1: Please upload at most 4 images.")
    uploaded_batch1 = uploaded_batch1[:4]

uploaded_batch2 = st.file_uploader(
    label="Upload images (batch 2 of 2, up to 4 pics)",
    type=["png", "jpg", "jpeg"],
    accept_multiple_files=True,
    key="batch2"
)
if len(uploaded_batch2) > 4:
    st.warning("Batch 2: Please upload at most 4 images.")
    uploaded_batch2 = uploaded_batch2[:4]

all_images = uploaded_batch1 + uploaded_batch2


# ─────────────────────────────────────────────────────────────────────────────
# 8) Email field
# ─────────────────────────────────────────────────────────────────────────────
recipient_email = st.text_input("Email To Send Report To", max_chars=100)


# ─────────────────────────────────────────────────────────────────────────────
# 9) Generate & Email button
# ─────────────────────────────────────────────────────────────────────────────
if st.button("Generate & Email Report"):
    if not visitor_name or not summary or not recipient_email:
        st.error("Please fill in all required fields: name, summary, and recipient email.")
    else:
        # 1) Prepare image byte streams
        image_bytes_list = [img for img in all_images]

        # 2) Generate the PDF (including address, time, temp, survey, and up to 8 images)
        pdf_path = generate_pdf(
            visitor_name,
            visit_date.strftime("%Y-%m-%d"),
            address,
            current_time_str,
            temperature_f,
            summary,
            survey_responses,
            image_bytes_list
        )

        # 3) Send email
        try:
            send_email(
                recipient_email,
                visitor_name,
                visit_date.strftime("%Y-%m-%d"),
                pdf_path
            )
            st.success(f"Email sent to {recipient_email}!")
        except Exception as e:
            st.error(f"Failed to send email: {e}")

        # 4) Clean up the temporary PDF file
        try:
            os.unlink(pdf_path)
        except:
            pass
