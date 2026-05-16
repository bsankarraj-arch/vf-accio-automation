import os
import base64
from email.message import EmailMessage
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def send_failure_email(error_details="No specific error details provided."):
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Token refresh failed: {e}. Re-authenticating...")
                creds = None
        
        if not creds:
            # PULL SECRETS FROM ENVIRONMENT VARIABLES
            client_config = {
                "installed": {
                    "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                    "project_id": "assio-automation",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                    "redirect_uris": ["http://localhost"]
                }
            }
            
            # Check if variables are missing
            if not client_config["installed"]["client_id"] or not client_config["installed"]["client_secret"]:
                print("❌ Error: GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not found in environment.")
                return

            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            creds = flow.run_local_server(port=0)
            
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('gmail', 'v1', credentials=creds)

        # Create the email container
        message = EmailMessage()
        
        # Email Body Content
        email_content = f"""
Dear Administrator,

The OIG Automation Bot has encountered an error during execution.

--- ERROR DETAILS ---
{error_details}
---------------------

Please investigate the logs for further information.

This is an automated message.
        """
        
        message.set_content(email_content)
        message['To'] = os.getenv("ALERT_EMAIL_TO", "mmohamed@verifiedfirst.com")
        message['From'] = os.getenv("ALERT_EMAIL_FROM", "vfaccioautomation@verifiedfirst.com")
        message['Subject'] = '⚠️ ALERT: OIG Bot Execution Failed'

        # Encode the message
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}

        # Send the message
        send_result = service.users().messages().send(userId="me", body=create_message).execute()
        print(f"Failure notification sent successfully! Message ID: {send_result['id']}")

    except Exception as error:
        print(f"An error occurred while sending the email: {error}")

if __name__ == '__main__':
    send_failure_email("Error: Manual script execution.")