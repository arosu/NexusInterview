import argparse
import logging
import os
import sys
from datetime import datetime, timedelta

import google.cloud.logging
import requests
import twitter

DELTA = 12  # Weeks
LOCATIONS = [
    ("Toronto Enrollment Center", 5027),
    ("Buffalo-Ft. Erie Enrollment Center", 5022),
    ("Niagara Falls Enrollment Center", 5161),
]

LOGGING_FORMAT = "%(asctime)s %(name)-12s %(levelname)-8s %(message)s"

SCHEDULER_API_URL = "https://ttp.cbp.dhs.gov/schedulerapi/locations/{location}/slots?startTimestamp={start}&endTimestamp={end}"
TTP_TIME_FORMAT = "%Y-%m-%dT%H:%M"

NOTIF_MESSAGE = "New appointment slot open at {location}: {date}"
MESSAGE_TIME_FORMAT = "%A, %B %d, %Y at %I:%M %p"


def tweet(message: str) -> None:

    api = twitter.Api(
        consumer_key=os.environ["CONSUMER_KEY"],
        consumer_secret=os.environ["CONSUMER_SECRET"],
        access_token_key=os.environ["ACCESS_TOKEN_KEY"],
        access_token_secret=os.environ["ACCESS_TOKEN_SECRET"],
    )
    try:
        api.PostUpdate(message)
    except twitter.TwitterError as e:
        if len(e.message) == 1 and e.message[0]["code"] == 187:
            logging.info("Tweet rejected (duplicate status)")
        else:
            raise

def check_for_openings(location_name: str, location_code: int, test_mode: bool = True) -> None:

    start = datetime.now()
    end = start + timedelta(weeks=DELTA)

    url = SCHEDULER_API_URL.format(
        location=location_code,
        start=start.strftime(TTP_TIME_FORMAT),
        end=end.strftime(TTP_TIME_FORMAT)
    )
    logging.info(f"Fetching data from {url}")

    try:
        results = requests.get(url).json()
    except requests.ConnectionError:
        logging.exception("Could not connect to scheduler API")
        sys.exit(1)

    for result in results:
        if result["active"] > 0:
            logging.info(f"Opening found for {location_name}")

            timestamp = datetime.strptime(result["timestamp"], TTP_TIME_FORMAT)
            message = NOTIF_MESSAGE.format(
                location=location_name,
                date=timestamp.strftime(MESSAGE_TIME_FORMAT)
            )
            if test_mode:
                print(message)
            else:
                logging.info("Tweeting: " + message)
                tweet(message)
            return  # Halt on first match

    logging.info(f"No openings for {location_name}")


def setup_logging(test_mode: bool) -> None:

    if test_mode:
        logging.basicConfig(
            format=LOGGING_FORMAT,
            level=logging.INFO,
            stream=sys.stdout
        )

    else:
        client = google.cloud.logging.Client()
        client.setup_logging()


def main() -> None:

    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", default=False)
    parser.add_argument("--verbose", action="store_true", default=False)
    args = parser.parse_args()

    setup_logging(args.test)

    logging.info("Starting checks (locations: {})".format(len(LOCATIONS)))
    for location_name, location_code in LOCATIONS:
        check_for_openings(location_name, location_code, args.test)


def google_cloud_entry(data, context):

    main()


if __name__ == "__main__":

    main()
