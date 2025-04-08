from typing import Optional, List
from datetime import datetime, timedelta
from pydantic import BaseModel
import logging
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os
from crewai import Agent, Task, Crew
from crewai.tools import tool
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import traceback

# Load environment variables
load_dotenv()
os.environ["OPENAI_API_KEY"] = ""

# Logging config
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@tool
def find_slot(duration_minutes: int = 60, timezone: str = "UTC") -> dict:
    """
    Find a free time slot of a given duration starting one hour from now.
    """
    now = datetime.now()
    start = now + timedelta(hours=1)
    end = start + timedelta(minutes=duration_minutes)
    return {
        "start_time": start.strftime('%Y-%m-%dT%H:%M:%S'),
        "end_time": end.strftime('%Y-%m-%dT%H:%M:%S'),
        "timezone": timezone
    }


@tool
def create_calendar_event(
    summary: str,
    start_time: str,
    end_time: str,
    attendees: List[str],
    description: Optional[str] = None,
    timezone: str = "UTC",
    credentials_path: str = './test.json',
    token_path: str = './token.json'
) -> dict:
    """
    Create a Google Calendar event with Google Meet link and send invitations to attendees.
    Reuses token to avoid repeated permissions.
    """
    scopes = [
        'https://www.googleapis.com/auth/calendar',
        'https://www.googleapis.com/auth/calendar.events'
    ]

    creds = None

    try:
        # Load credentials from token file (JSON format)
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, scopes)

        # Refresh or create new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, scopes)
                creds = flow.run_local_server(port=0)

            # Save new token
            with open(token_path, 'w') as token_file:
                token_file.write(creds.to_json())

        # Build Google Calendar service
        service = build('calendar', 'v3', credentials=creds)

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
        traceback.print_exc()
        return {
            'status': 'error',
            'error_message': str(e)
        }


# --- Crew Setup ---
def create_scheduling_crew():
    llm = ChatOpenAI(model="gpt-4-turbo", temperature=0.3)

    slot_finder_agent = Agent(
        role="Slot Finder",
        goal="Identify available time slots for meetings",
        backstory="You are an expert at checking calendar availability and suggesting open times.",
        tools=[find_slot],
        verbose=True,
        allow_delegation=False,
        llm=llm
    )

    scheduler_agent = Agent(
        role="Calendar Scheduler",
        goal="Create calendar events efficiently",
        backstory="You are a calendar expert using tools to automate Google Calendar events.",
        tools=[find_slot, create_calendar_event],
        verbose=True,
        allow_delegation=False,
        llm=llm
    )

    find_slot_task = Task(
        description="Find a suitable 60-minute time slot starting one hour from now in UTC.",
        expected_output="A dictionary with start_time, end_time, and timezone.",
        agent=scheduler_agent
    )

    create_event_task = Task(
        description="""
        Create a Google Calendar event with:
        - Title: Project Kickoff Meeting for 4
        - Description: Initial meeting to discuss project goals and timelines.
        - Timezone: UTC (use from previous task)
        - Attendees: mohammmadabubakar990@gmail.com, iam.abu.017@gmail.com
        - Include Google Meet link
        - Use default reminders
        - Send email notifications to attendees
        - Credentials path: ./test.json
        - token_path: Path to cached token (default: ./token.json)
        """,
        expected_output="A dictionary with event_link, meet_link, event_id, status.",
        agent=scheduler_agent
    )

    return Crew(
        agents=[scheduler_agent, slot_finder_agent],
        tasks=[find_slot_task, create_event_task],
        verbose=True,
        memory=True
    )


# --- Main ---
if __name__ == "__main__":
    try:
        crew = create_scheduling_crew()
        result = crew.kickoff()
        print("\n🎯 Final Result:\n", result)
    except Exception as e:
        logger.error(f"Error in scheduling workflow: {e}")
