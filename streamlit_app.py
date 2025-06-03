import os
import tempfile
import smtplib
from email.message import EmailMessage
from datetime import date

import streamlit as st
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# 1) Page config
st.set_page_config(page_title="Site Visit Report", layout="centered")

# 2) Helper: generate PDF with embedded images
def generate_pdf(visitor, visit_date, summary, image_files):
    tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    c = canvas.Canvas(tmp_pdf.name, pagesize=letter)
    width, height = letter

    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, "Site Visit Report")

    # Visitor Info
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 80, f"Visitor: {visitor}")
    c.drawString(50, height - 100, f"Date: {visit_date}")

    # Summary text
    text_obj = c.beginText(50, height - 140)
    text_obj.setFont("Helvetica", 12)
    for line in summary.split("\n"):
        text_obj.textLine(line)
    c.drawText(text_obj)

    # Place each image, scaled to max width=200
    y_pos = height - 250
    for img_bytes in image_files:
        try:
            img = ImageReader(img_bytes)
            iw, ih = img.getSize()
            aspect = ih / iw
            img_w = 200
            img_h = 200 * aspect
            # New page if there’s no room
            if y_pos - img_h < 50:
                c.showPage()
                y_pos = height - 50
            c.drawImage(img, 50, y_pos - img_h, width=img_w, height=img_h)
            y_pos -= (img_h + 20)
        except Exception:
            continue

    c.showPage()
    c.save()
    return tmp_pdf.name  # path to the PDF file

# 3) Helper: send email with attachments
def send_email(recipient, visitor, visit_date, pdf_path, video_paths):
    EMAIL_USER = os.getenv("STREAMLIT_EMAIL_USER")
    EMAIL_PASS = os.getenv("STREAMLIT_EMAIL_PASS")

    msg = EmailMessage()
    msg["Subject"] = f"Site Visit Report from {visitor}"
    msg["From"] = EMAIL_USER
    msg["To"] = recipient
    msg.set_content(
        f"Hello,\n\n"
        f"Attached is the site visit report (PDF) by {visitor} on {visit_date}.\n"
        f"Videos (if any) are attached separately.\n\n"
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

    # Attach each video
    for vid_path in video_paths:
        with open(vid_path, "rb") as vf:
            vdata = vf.read()
        vname = os.path.basename(vid_path)
        msg.add_attachment(
            vdata,
            maintype="application",
            subtype="octet-stream",
            filename=vname
        )

    # Send via SMTP (example uses Gmail)
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)

# 4) Streamlit UI
st.title("Site Visit Report 📝")

visitor_name = st.text_input("Your Name", max_chars=50)
visit_date = st.date_input("Date of Visit", value=date.today())
summary = st.text_area("Brief Summary", help="Describe what you saw/did on site", height=120)

uploaded_images = st.file_uploader(
    label="Upload up to 4 images",
    type=["png", "jpg", "jpeg"],
    accept_multiple_files=True
)
if len(uploaded_images) > 4:
    st.warning("Please upload at most 4 images.")
    uploaded_images = uploaded_images[:4]

uploaded_videos = st.file_uploader(
    label="Upload up to 2 videos",
    type=["mp4", "mov", "avi"],
    accept_multiple_files=True
)
if len(uploaded_videos) > 2:
    st.warning("Please upload at most 2 videos.")
    uploaded_videos = uploaded_videos[:2]

recipient_email = st.text_input("Email To Send Report To", max_chars=100)

if st.button("Generate & Email Report"):
    if not visitor_name or not summary or not recipient_email:
        st.error("Please fill in all required fields: name, summary, and recipient email.")
    else:
        # 1) Collect image bytes
        image_bytes_list = [img for img in uploaded_images]

        # 2) Save videos to temp files
        video_temp_paths = []
        for vid_file in uploaded_videos:
            suffix = os.path.splitext(vid_file.name)[1]
            tmp_vid = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp_vid.write(vid_file.getbuffer())
            tmp_vid.close()
            video_temp_paths.append(tmp_vid.name)

        # 3) Generate the PDF
        pdf_path = generate_pdf(
            visitor_name,
            visit_date.strftime("%Y-%m-%d"),
            summary,
            image_bytes_list
        )

        # 4) Send email
        try:
            send_email(
                recipient_email,
                visitor_name,
                visit_date.strftime("%Y-%m-%d"),
                pdf_path,
                video_temp_paths
            )
            st.success(f"Email sent to {recipient_email}!")
        except Exception as e:
            st.error(f"Failed to send email: {e}")

        # 5) Clean up temp files
        try:
            os.unlink(pdf_path)
        except:
            pass
        for path in video_temp_paths:
            try:
                os.unlink(path)
            except:
                pass
