import time
from datetime import datetime
from playsound import playsound
from playwright.sync_api import sync_playwright, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

# Path to your sound file
SOUND_FILE = "siren.wav"

# The last acceptable appointment date
TRIP_DATE = datetime(2025, 8, 15)

# Your session token URL
SESSIONS_TOKEN_URL = (
    "https://www.ch-edoc-reservation.admin.ch/#/session?"
    "token=******&locale=en-US"
)

def play_alert_sound():
    """Play the alert siren."""
    playsound(SOUND_FILE)

def check_and_rebook(page: Page):
    """
    Opens the schedule page, clicks through to the earliest appointment,
    compares dates, and if it's earlier than TRIP_DATE, plays a sound
    and attempts to rebook.
    """
    # 1) Go to session page
    page.goto(SESSIONS_TOKEN_URL, wait_until="networkidle")

    # 2) Click the "Re-schedule" button
    # Comment this line out if no current schedule
    # page.click("#rebookBtn")

    # 3) Click the "Earliest slot" button
    page.click("#bookingListBtn")

    now = datetime.now()
    print(f"[{now:%Y-%m-%d %H:%M:%S}] Checking earliest appointment…")

    # give table a moment to render
    time.sleep(1)

    # 4) Scrape the date text from the first row
    #    Example cell text: "Tu. 01.10.2024"
    try:
        # Try to fetch cell content quickly (2 sec timeout)
        cell = page.locator('//table[@class="mat-table cdk-table"]/tbody/tr[1]/td[1]')
        cell.wait_for(timeout=2000)  # 2 seconds max
        cell_text = cell.text_content()
        if not cell_text:
            raise RuntimeError("Appointment cell found but empty.")
    except PlaywrightTimeoutError:
        raise RuntimeError("Could not find appointment cell within 2 seconds.")

    # remove "Tu.", "Mo.", etc. → "01.10.2024"
    date_str = cell_text.split(".", maxsplit=1)[1].strip()
    earliest_date = datetime.strptime(date_str, "%d.%m.%Y")

    is_earlier = earliest_date < TRIP_DATE
    print(f"Earliest appointment: {earliest_date:%Y-%m-%d}")
    print(f"Is earlier than desired ({TRIP_DATE:%Y-%m-%d})? {is_earlier}")

    # 5) If the earliest slot is earlier than our trip date, alert & rebook
    while is_earlier:
        play_alert_sound()

        # click that first available slot
        page.click(
            '//table[@class="mat-table cdk-table"]/tbody/tr[1]/td[1]'
        )

        # click the final "Re-book" button
        page.click("#rebookBtn")

        # optionally break out if you only want one rebook attempt:
        # break

    print("…Done checking & (if applicable) rebooking.")

def main():
    with sync_playwright() as pw:
        # Launch Firefox (change to pw.chromium or pw.webkit as desired)
        browser = pw.firefox.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        try:
            while True:
                try:
                    check_and_rebook(page)
                except Exception as e:
                    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Error during check:", e)
                finally:
                    # Wait before next iteration
                    time.sleep(5)
        finally:
            context.close()
            browser.close()

if __name__ == "__main__":
    main()
