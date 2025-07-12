import time
from datetime import datetime
from playsound import playsound
from playwright.sync_api import sync_playwright, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
import re

# Path to your sound file
SOUND_FILE = "siren.wav"

# The lastest acceptable appointment date
TRIP_DATE = datetime(2026, 8, 15)

# Your session token URL
SESSIONS_TOKEN_URL = (
    "https://www.ch-edoc-reservation.admin.ch/#/session?"
    "token=******&locale=en-US"
)

now = datetime.now()

def play_alert_sound():
    """Play the alert siren."""
    playsound(SOUND_FILE)

def detect_page_type_and_existing_date(page: Page):
    """
    Detect if the page has an existing appointment or not.
    Returns: tuple (page_type, existing_date)
    - page_type: 'with_appointment' or 'without_appointment'
    - existing_date: datetime object if existing appointment found, None otherwise
    """
    try:
        # Wait for page to load
        page.wait_for_load_state("networkidle", timeout=500)

        # Wait a bit more to ensure dynamic content is loaded

        time.sleep(2)
        
        # Check if re-schedule button exists (indicates existing appointment)
        reschedule_btn = page.locator("#rebookBtn")
        if reschedule_btn.is_visible():
            print(f"[{now:%Y-%m-%d %H:%M:%S}] Detected: Page with existing appointment")
            
            # Try to extract existing appointment date
            existing_date = extract_existing_appointment_date(page)
            return 'with_appointment', existing_date
           
        # Check if earliest slot button exists (indicates no existing appointment)
        earliest_btn = page.locator("#bookingListBtn")
        if earliest_btn.is_visible():
            print(f"[{now:%Y-%m-%d %H:%M:%S}] Detected: Page ready for booking")
            return 'without_appointment', None
            
    except PlaywrightTimeoutError:
        print(f"[{now:%Y-%m-%d %H:%M:%S}] Could not detect page type within timeout")
        
    return 'unknown', None

def extract_existing_appointment_date(page: Page):
    """
    Extract the existing appointment date from the specific app-appointment-detail section.
    Returns: datetime object or None if not found
    """
    try:
        # Look for the appointment detail section
        appointment_detail = page.locator('app-appointment-detail')
        
        if appointment_detail.count() > 0:
            text = appointment_detail.first.text_content()
            if text:
                # Look for the specific date pattern: "**Date: **Th. 28.08.2025"
                date_pattern = r'Date:\s*[A-Za-z]{2,3}\.\s*(\d{1,2}\.\d{1,2}\.\d{4})'
                match = re.search(date_pattern, text)
                
                if match:
                    date_str = match.group(1)  # Extract "28.08.2025"
                    try:
                        date = datetime.strptime(date_str, "%d.%m.%Y")
                        print(f"[{now:%Y-%m-%d %H:%M:%S}] Found existing appointment date: {date:%Y-%m-%d}")
                        return date
                    except ValueError:
                        print(f"[{now:%Y-%m-%d %H:%M:%S}] Could not parse date: {date_str}")
                else:
                    print(f"[{now:%Y-%m-%d %H:%M:%S}] Date pattern not found in appointment detail")
                    print(f"Text content: {text[:200]}...")  # Show first 200 chars for debugging
                    
    except Exception as e:
        print(f"[{now:%Y-%m-%d %H:%M:%S}] Error extracting appointment date: {e}")
    
    print(f"[{now:%Y-%m-%d %H:%M:%S}] Could not find existing appointment date")
    return None

def check_and_rebook(page: Page):
    """
    Opens the schedule page, detects the page type, and handles both scenarios:
    - Pages with existing appointments (needs re-scheduling)
    - Pages without appointments (direct booking)
    - Clicks through to the earliest appointment, compares dates, 
    - and if it's earlier than TRIP_DATE, attempts to book/rebook and plays a sound.
    """
    # 1) Go to session page
    page.goto(SESSIONS_TOKEN_URL, wait_until="networkidle")
    
    # 2) Detect what type of page we're on and get existing appointment date
    page_type, existing_date = detect_page_type_and_existing_date(page)
    
    # 3) Determine the target date to beat
    target_date = TRIP_DATE
    if existing_date and existing_date < TRIP_DATE:
        target_date = existing_date
        print(f"[{now:%Y-%m-%d %H:%M:%S}] Using existing appointment date as target: {target_date:%Y-%m-%d}")
    else:
        print(f"[{now:%Y-%m-%d %H:%M:%S}] Using original trip date as target: {target_date:%Y-%m-%d}")

    if page_type == 'with_appointment':
        # Click the "Re-schedule" button for existing appointments
        try:
            page.click("#rebookBtn")
            print(f"[{now:%Y-%m-%d %H:%M:%S}] Clicked re-schedule button")
        except PlaywrightTimeoutError:
            print(f"[{now:%Y-%m-%d %H:%M:%S}] Could not find re-schedule button")
            return
    elif page_type == 'without_appointment':
        print(f"[{now:%Y-%m-%d %H:%M:%S}] No existing appointment found, proceeding with direct booking")
    else:
        print(f"[{now:%Y-%m-%d %H:%M:%S}] Unknown page type, attempting to proceed anyway")

    # 4) Click the "Earliest slot" button
    try:
        page.click("#bookingListBtn")
        print(f"[{now:%Y-%m-%d %H:%M:%S}] Clicked earliest slot button")
    except PlaywrightTimeoutError:
        print(f"[{now:%Y-%m-%d %H:%M:%S}] Could not find earliest slot button")
        return

    print(f"[{now:%Y-%m-%d %H:%M:%S}] Checking earliest appointment…")

    # Give table a moment to render
    time.sleep(1)

    # 5) Scrape the date text from the first row
    #    Example cell text: "Tu. 01.10.2024"
    try:
        # Try to fetch cell content quickly
        cell = page.locator('//table[@class="mat-table cdk-table"]/tbody/tr[1]/td[1]')
        cell.wait_for(timeout=1000)
        cell_text = cell.text_content()
        if not cell_text:
            raise RuntimeError("Appointment cell found but empty.")
    except PlaywrightTimeoutError:
        raise RuntimeError("Could not find appointment cell within timeout.")

    # Remove day abbreviation → "01.10.2024"
    date_str = cell_text.split(".", maxsplit=1)[1].strip()
    earliest_date = datetime.strptime(date_str, "%d.%m.%Y")

    is_earlier = earliest_date < target_date
    print(f"[{now:%Y-%m-%d %H:%M:%S}] Target date: {target_date:%Y-%m-%d}")
    print(f"[{now:%Y-%m-%d %H:%M:%S}] Is earlier than target? {is_earlier}")

    # 6) If the earliest slot is earlier than our target date, alert & book/rebook
    if is_earlier:
        print(f"[{now:%Y-%m-%d %H:%M:%S}] Found earlier appointment! Attempting to book...")
        
        # Click that first available slot
        try:
            page.click('//table[@class="mat-table cdk-table"]/tbody/tr[1]/td[1]')
            print(f"[{now:%Y-%m-%d %H:%M:%S}] Selected earliest appointment slot")
        except PlaywrightTimeoutError:
            print(f"[{now:%Y-%m-%d %H:%M:%S}] Could not click on appointment slot")
            return

        # Handle booking based on page type
        if page_type == 'with_appointment':
            # For re-scheduling existing appointment
            try:
                # Click the final "Re-book" button
                page.click("#rebookBtn", timeout=1000)
                print(f"[{now:%Y-%m-%d %H:%M:%S}] Clicked re-book button for existing appointment")
            except PlaywrightTimeoutError:
                print(f"[{now:%Y-%m-%d %H:%M:%S}] Could not find re-book button")
                return
        else:
            # For new booking
            try:
                # Click book button
                page.click("#bookBtn", timeout=1000)
                print(f"[{now:%Y-%m-%d %H:%M:%S}] Clicked book button for new appointment")
            except PlaywrightTimeoutError:
                print(f"[{now:%Y-%m-%d %H:%M:%S}] Could not find book button")
                return

        # Play alert sound
        play_alert_sound()
        print(f"[{now:%Y-%m-%d %H:%M:%S}] ✅ Successfully booked earlier appointment!")
        
        # Wait a bit to see the result
        time.sleep(2)
    else:
        print(f"[{now:%Y-%m-%d %H:%M:%S}] No earlier appointments available.")

    print(f"[{now:%Y-%m-%d %H:%M:%S}] …Done checking & (if applicable) rebooking.")

def main():
    with sync_playwright() as pw:
        # Launch Firefox (change to pw.chromium or pw.webkit as desired)
        browser = pw.firefox.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        wait_time = 1

        try:
            while True:
                try:
                    check_and_rebook(page)
                except Exception as e:
                    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Error during check:", e)
                finally:
                    # Wait before next iteration
                    print(f"[{now:%Y-%m-%d %H:%M:%S}] Waiting {wait_time} seconds before next check...")
                    time.sleep(wait_time)
        except KeyboardInterrupt:
            print(f"[{now:%Y-%m-%d %H:%M:%S}] \n🛑 Script stopped by user")
        finally:
            context.close()
            browser.close()

if __name__ == "__main__":
    main()