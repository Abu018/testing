from typing import List, Optional
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request  # <-- Fix for token refresh
import os


def find_slot(duration_minutes: int = 60, timezone: str = "UTC") -> (str, str):
    """
    Find a suitable date/time slot. Returns the next hour from now.
    """
    now = datetime.utcnow()
    start = now + timedelta(hours=1)
    end = start + timedelta(minutes=duration_minutes)

    start_iso = start.strftime('%Y-%m-%dT%H:%M:%S')
    end_iso = end.strftime('%Y-%m-%dT%H:%M:%S')
    return start_iso, end_iso


def get_calendar_service(credentials_path: str = './test.json', token_path: str = 'token.json'):
    """
    Authenticate and return Google Calendar API service with token caching.
    """
    scopes = ['https://www.googleapis.com/auth/calendar', 'https://www.googleapis.com/auth/calendar.events']
    creds = None

    # Load existing token if it exists
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, scopes)

    # If no valid credentials, run login flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())  # refresh token
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, scopes)
            creds = flow.run_local_server(port=0)
        # Save token for future use
        with open(token_path, 'w') as token_file:
            token_file.write(creds.to_json())

    return build('calendar', 'v3', credentials=creds)


def create_calendar_event(
    summary: str,
    start_time: str,
    end_time: str,
    attendees: List[str],
    description: Optional[str] = None,
    timezone: str = "UTC",
    credentials_path: str = './test.json',
    token_path: str = 'token.json'
) -> dict:
    """
    Create a Google Calendar event with Google Meet link and invitations.
    """
    try:
        service = get_calendar_service(credentials_path, token_path)

        event = {
            'summary': summary,
            'description': description,
            'start': {'dateTime': start_time, 'timeZone': timezone},
            'end': {'dateTime': end_time, 'timeZone': timezone},
            'attendees': [{'email': email} for email in attendees],
            'conferenceData': {
                'createRequest': {
                    'requestId': f"event_{datetime.now().timestamp()}",
                    'conferenceSolutionKey': {'type': 'hangoutsMeet'}
                }
            },
            'reminders': {'useDefault': True},
            'guestsCanModify': True,
            'guestsCanInviteOthers': True,
            'guestsCanSeeOtherGuests': True
        }

        created_event = service.events().insert(
            calendarId='primary',
            body=event,
            conferenceDataVersion=1,
            sendUpdates='all'
        ).execute()

        return {
            'status': 'success',
            'event_link': created_event.get('htmlLink'),
            'meet_link': created_event.get('hangoutLink'),
            'event_id': created_event.get('id')
        }

    except Exception as e:
        return {
            'status': 'error',
            'error_message': str(e)
        }


# 🔧 Example usage
if __name__ == "__main__":
    start, end = find_slot()
    event_details = create_calendar_event(
        summary="Project Meeting with auto find slot",
        description="Discussion about next steps for the project",
        start_time=start,
        end_time=end,
        attendees=[
            "iam.abu.017@gmail.com"
        ],
        timezone="UTC",
        credentials_path="./test.json",
        token_path="token.json"
    )

    print("Event Result:")
    for key, value in event_details.items():
        print(f"{key}: {value}")
