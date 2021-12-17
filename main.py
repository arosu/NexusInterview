import datetime as dt
import logging
import os
import time
from enum import Enum

import google.cloud.logging
import smtplib
import requests
from twilio.rest import Client

logger = logging.getLogger(__name__)

NUM_RETRIES = 5
SLEEP_TIME = 0.05

CURRENT_APPOINTMENT = (5161, dt.datetime(year=2022, month=1, day=31))
DATE_FORMAT = "%Y-%m-%dT%H:%M"
LOCATIONS = {
    5161: "Niagara Falls Enrollment Center",
    5022: "Buffalo-Ft. Erie Enrollment Center",
    5520: "Lansdowne, ON",
    5027: "Toronto Enrollment Center",
}
URL_TEMPLATE = "https://ttp.cbp.dhs.gov/schedulerapi/slots?orderBy=soonest&limit=3&locationId={location_id}&minimum=1"


def retry_get_request(url: str, num_retries: int) -> requests.Response:

    while True:
        num_retries -= 1
        try:
            return requests.get(url)
        except requests.exceptions.ConnectionError:
            if num_retries == 0:
                raise
            else:
                time.sleep(SLEEP_TIME)


def get_appointments() -> list[dict]:

    appointments = []
    for id, location in LOCATIONS.items():

        url = URL_TEMPLATE.format(location_id=id)
        logger.info(f"{id=}, {location=}, {url=} | sending GET request")

        for appt in retry_get_request(url, NUM_RETRIES).json():
            if (
                appt["locationId"] == CURRENT_APPOINTMENT[0]
                and dt.datetime.strptime(appt["startTimestamp"], DATE_FORMAT) >= CURRENT_APPOINTMENT[1]
            ):
                continue

            appointments.append(appt)

        time.sleep(SLEEP_TIME)

    return appointments


def parse_appointments(appointments: list[dict]) -> str:

    logger.info(f"{appointments=} | parsing appointments")

    message = "FOUND APPOINTMENTS:"
    for appointment in appointments:

        location = LOCATIONS[appointment["locationId"]]
        time = appointment["startTimestamp"]

        message += f"\n\n* {location} at {time}"

    message += "\n\nhttps://ttp.cbp.dhs.gov/"

    return message


def send_text_message(message: str) -> None:

    logger.info(f"{message=} | sending text message")

    account_sid = os.environ["TWILIO_ACCOUNT_SID"]
    auth_token = os.environ["TWILIO_AUTH_TOKEN"]
    client = Client(account_sid, auth_token)

    message = client.messages.create(
        body=message,
        from_="+19704428745",
        to='+16467346769'
    )


def send_email(body: str) -> None:

    logger.info(f"{body=} | sending email")

    gmail_user = os.environ["GMAIL_USER"]
    gmail_password = os.environ["GMAIL_PASSWORD"]

    sent_from = gmail_user
    to = [gmail_user]

    email_text = f"Subject: Nexus Appointments\n\n{body}"

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(gmail_user, gmail_password)
        server.sendmail(sent_from, to, email_text)
        server.close()
        logger.info(f"{sent_from=}, {to=} | successfully sent email")

    except:
        logger.info(f"{sent_from=}, {to=} | failed to send email")
        raise


def nexus() -> None:

    if appointments := get_appointments():
        logger.info("found appointments | nexus")
        message = parse_appointments(appointments)
        send_email(message)

    else:
        logger.info("did not find any appointments | nexus")


def setup_logging() -> None:

    client = google.cloud.logging.Client()
    client.setup_logging()


def main(data, context) -> None:

    setup_logging()
    nexus()