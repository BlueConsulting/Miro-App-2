import os

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import ssl
# from django.template.loader import render_to_string



def send_email(sender_email, password, recipient_email, subject, body):
        try:
            # Create an SSL context with lower security level
            context = ssl.create_default_context()
            context.set_ciphers("HIGH:!DH:!aNULL")
            # context.set_ciphers("DEFAULT:@SECLEVEL=1")  # Lower the security level to 1

            # Set up the email details
            msg = MIMEMultipart()
            msg['From'] = sender_email
            msg['To'] = recipient_email
            msg['Subject'] = subject

            # Attach the email body
            msg.attach(MIMEText(body, 'html'))

            # Connect to the SMTP server using port 587 with TLS
            server = smtplib.SMTP('smtp.rediffmailpro.com', 587)
            server.ehlo()  # Identify yourself to the server
            server.starttls(context=context)  # Secure the connection using the context
            # server.set_debuglevel(1)

            print("This1 ----> Connection successful!")
            # Log in to the server
            server.login(sender_email, password)
            print("This2 ----> Connection successful!")
            # Send the email
            server.sendmail(sender_email, recipient_email, msg.as_string())
            print("Email sent successfully!")

            # Disconnect from the server
            server.quit()

        except Exception as e:
            print(f"Failed to send email: {e}")

from django.db import connection





if __name__ == "__main__":
    sender_email = 'nasim.ahmed@blueconsulting.co.in'
    # password = 'India@1234'
    # recipient_email = 'nasim.blueconsulting@gmail.com'
    # subject = 'Test Sibjrct'
    # message = '''
    #     <html>
    #         <body>
    #             <p>Dear {user},</p>
    #             <p>Click the link below to reset your password:</p>
    #             <p><a href="{link}">Reset Password</a></p>
    #         </body>
    #     </html>
    # '''.format(user=recipient_email, link='http://127.0.0.1:8000/signup/')
    # body = ''
    # send_email(sender_email, password, recipient_email, subject, message)