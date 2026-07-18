# app.py - Full Onda Booking Bot with Webhook + Telegram + Multiple Courts (Sabay)
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import requests
from datetime import datetime, timedelta
import time
import json
import threading
import os
import base64
from io import BytesIO

app = Flask(__name__)

# ═══════════════════════════════════════════════════════════════
# TELEGRAM CONFIGURATION - PALITAN MO TO
# ═══════════════════════════════════════════════════════════════
TELEGRAM_BOT_TOKEN = "8911007553:AAHvDQCtA5R9yp2gQN-0irF6tPb-HjiOJ8k"
TELEGRAM_CHAT_ID = "-5427084407"

# ═══════════════════════════════════════════════════════════════
# BOOKING CONFIGURATION
# ═══════════════════════════════════════════════════════════════
MAX_COURTS_TO_BOOK = 2
BOOK_ANY_AVAILABLE = True

# ═══════════════════════════════════════════════════════════════
# TELEGRAM FUNCTIONS
# ═══════════════════════════════════════════════════════════════
def send_telegram_message(message):
    """Send text message to Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, data=data)
        print(f"✅ Telegram message sent")
        return True
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return False

def send_telegram_photo(photo_bytes, caption=""):
    """Send photo to Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        files = {'photo': ('screenshot.png', photo_bytes, 'image/png')}
        data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption}
        response = requests.post(url, files=files, data=data)
        print(f"✅ Telegram photo sent")
        return True
    except Exception as e:
        print(f"❌ Telegram photo error: {e}")
        return False

def take_screenshot(page, filename="screenshot.png"):
    """Take screenshot and send to Telegram"""
    try:
        screenshot_bytes = page.screenshot(full_page=False)
        send_telegram_photo(screenshot_bytes, "📸 Booking progress screenshot")
        with open(filename, "wb") as f:
            f.write(screenshot_bytes)
        print(f"✅ Screenshot saved: {filename}")
        return screenshot_bytes
    except Exception as e:
        print(f"❌ Failed to take screenshot: {e}")
        return None

# ═══════════════════════════════════════════════════════════════
# BOOKING FUNCTIONS
# ═══════════════════════════════════════════════════════════════
def get_availability(page, date_api):
    """Kumuha ng availability data mula sa API para sa specific date"""
    facility_id = "5f8786bd-dc61-4509-b893-74cda8f783f7"
    api_url = f"https://app.onda.fit/api/public/facilities/{facility_id}/date-availability"
    
    params = {
        "startDate": date_api,
        "endDate": date_api,
        "duration": 60,
        "includeSchedule": "true"
    }
    
    cookies = page.context.cookies()
    cookie_string = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
    
    headers = {
        "accept": "application/json",
        "cookie": cookie_string,
        "referer": "https://app.onda.fit/book/thirsty-pickle"
    }
    
    response = requests.get(api_url, params=params, headers=headers, timeout=30)
    return response.json()

def get_all_available_slots(data, target_times, time_display, court_names):
    """Kunin ang lahat ng available slots sa target times"""
    if not data.get("success"):
        return []
    
    slots_by_space = data["data"]["slotsBySpace"]
    available_slots = []
    
    for start_time in target_times:
        for space_id, slots in slots_by_space.items():
            court_name = court_names.get(space_id, space_id[:8])
            
            for slot in slots:
                if slot["startTime"] == start_time and slot["isAvailable"]:
                    available_slots.append({
                        "court": court_name,
                        "space_id": space_id,
                        "display": time_display[start_time],
                        "startTime": start_time,
                        "endTime": slot["endTime"]
                    })
    
    return available_slots

def select_slot_fast(page, slot):
    """Pumili ng slot - MAS MABILIS at DIRECT"""
    try:
        court = slot['court']
        display = slot['display']
        print(f"  Selecting: {court} @ {display}")
        
        # Direct click sa button - gamit ang exact text
        # Ang button ay may text na "Court X @ Time"
        selector = f'button:has-text("{court} @ {display}")'
        
        btn = page.locator(selector).first
        if btn.count() > 0:
            btn.click(timeout=2000)
            page.wait_for_timeout(300)
            print(f"    ✓ Selected!")
            return True
        
        # Alternative: Hanapin ang button na may court at time
        selector2 = f'button:has-text("{court}")'
        btns = page.locator(selector2).all()
        for b in btns:
            text = b.inner_text()
            if display in text and "available" in text.lower():
                b.click(timeout=2000)
                page.wait_for_timeout(300)
                print(f"    ✓ Selected! (alt)")
                return True
        
        print(f"    ✗ Cannot find button")
        return False
    except Exception as e:
        print(f"    ✗ Error: {e}")
        return False

def select_multiple_slots(page, slots_to_book, date):
    """Pumili ng multiple slots nang sabay - WITHOUT triggering Proceed agad"""
    try:
        print(f"\n📌 SELECTING {len(slots_to_book)} COURT(S) SABAY!")
        
        # I-click ang calendar para makita ang slots
        page.get_by_label("Select booking date").click()
        page.wait_for_timeout(1000)
        
        # I-click ang date
        date_btn = page.locator(f'button[data-day="{date}"]').first
        if date_btn.count() > 0 and not date_btn.is_disabled():
            date_btn.click()
            page.wait_for_timeout(1500)
        
        # Piliin ang lahat ng slots (sabay-sabay)
        for idx, slot in enumerate(slots_to_book, 1):
            print(f"\n  [{idx}] Selecting: {slot['court']} @ {slot['display']}")
            
            # Hanapin ang button
            selector = f'button:has-text("{slot["court"]} @ {slot["display"]}")'
            btn = page.locator(selector).first
            
            if btn.count() > 0:
                # I-check kung available
                if "available" in btn.inner_text().lower():
                    btn.click(timeout=2000)
                    page.wait_for_timeout(300)
                    print(f"    ✓ Selected!")
                else:
                    print(f"    ✗ Not available anymore!")
                    return False
            else:
                # Alternative selector
                alt_selector = f'button:has-text("{slot["court"]}")'
                btns = page.locator(alt_selector).all()
                found = False
                for b in btns:
                    text = b.inner_text()
                    if slot["display"] in text and "available" in text.lower():
                        b.click(timeout=2000)
                        page.wait_for_timeout(300)
                        print(f"    ✓ Selected! (alt)")
                        found = True
                        break
                if not found:
                    print(f"    ✗ Cannot find button")
                    return False
        
        print(f"\n✅ All {len(slots_to_book)} slots selected!")
        return True
        
    except Exception as e:
        print(f"❌ Error selecting slots: {e}")
        return False

def click_proceed_after_select(page):
    """Hanapin at i-click ang Proceed button"""
    try:
        proceed_btn = page.locator('button:has-text("Proceed")').first
        
        if proceed_btn.count() > 0:
            print("✓ Found Proceed button!")
            proceed_btn.click()
            print("✓✓✓ Clicked Proceed button!")
            return True
        else:
            print("✗ Proceed button not found")
            return False
    except Exception as e:
        print(f"✗ Error clicking Proceed: {e}")
        return False

def fill_booking_form(page, name, phone, email):
    """Punan ang booking form"""
    try:
        print("Filling Full Name...")
        name_input = page.locator('input[aria-label="Full Name"]').first
        if name_input.count() > 0:
            name_input.click()
            name_input.fill("")
            name_input.fill(name)
            print(f"✓ Name filled: {name}")
        
        page.wait_for_timeout(500)
        
        print("Filling Phone Number...")
        phone_input = page.locator('input[aria-label="Phone Number"]').first
        if phone_input.count() > 0:
            phone_input.click()
            phone_input.fill("")
            phone_input.fill(phone)
            print(f"✓ Phone filled: {phone}")
        
        page.wait_for_timeout(500)
        
        print("Filling Email Address...")
        email_input = page.locator('input[aria-label="Email Address"]').first
        if email_input.count() > 0:
            email_input.click()
            email_input.fill("")
            email_input.fill(email)
            print(f"✓ Email filled: {email}")
        
        page.wait_for_timeout(500)
        print("  Waiting 3 seconds...")
        time.sleep(3)
        
        return True
    except Exception as e:
        print(f"✗ Error filling form: {e}")
        return False

def click_form_proceed(page):
    """I-click ang Proceed button sa form"""
    try:
        print("Clicking Proceed button on form...")
        proceed_btn = page.locator('button:has-text("Proceed")').first
        
        if proceed_btn.count() > 0:
            proceed_btn.click()
            print("✓✓✓ Form Proceed button clicked!")
            return True
        else:
            print("✗ Proceed button not found on form")
            return False
    except Exception as e:
        print(f"✗ Error clicking form Proceed: {e}")
        return False

def click_terms_and_proceed(page):
    """I-click ang terms checkbox at Proceed button"""
    try:
        print("  Waiting 2 seconds...")
        time.sleep(2)
        
        print("Clicking Terms checkbox...")
        terms_checkbox = page.locator('input[id="terms-accepted"]').first
        if terms_checkbox.count() > 0:
            terms_checkbox.click()
            print("✓ Terms checkbox clicked!")
        
        page.wait_for_timeout(500)
        
        print("Clicking Confirm & Proceed to Payment...")
        confirm_btn = page.locator('button:has-text("Confirm & Proceed to Payment")').first
        if confirm_btn.count() > 0:
            confirm_btn.click()
            print("✓✓✓ Confirm & Proceed to Payment clicked!")
            return True
        else:
            confirm_alt = page.locator('button:has-text("Payment")').first
            if confirm_alt.count() > 0:
                confirm_alt.click()
                print("✓✓✓ Payment button clicked (alternative)!")
                return True
            else:
                print("✗ Cannot find Confirm & Proceed to Payment button")
                return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def select_qrph_payment(page):
    """Piliin ang QRPH payment method at mag-screenshot"""
    try:
        print("Waiting for payment options to load...")
        page.wait_for_timeout(2000)
        
        print("Selecting QRPH payment method...")
        qrph_selector = 'div[role="button"][aria-label="Select QRPH payment method"]'
        qrph_btn = page.locator(qrph_selector).first
        
        if qrph_btn.count() > 0:
            qrph_btn.click()
            print("✓ QRPH payment method selected!")
            page.wait_for_timeout(2000)
            
            print("Waiting for QR code to load...")
            page.wait_for_timeout(3000)
            print("✓ QR code should be visible now!")
            
            screenshot = page.screenshot(full_page=False)
            send_telegram_photo(
                screenshot,
                f"✅ <b>QR CODE READY!</b>\n\nPlease scan to complete payment."
            )
            
            return True
        else:
            print("✗ QRPH payment option not found")
            return False
    except Exception as e:
        print(f"✗ Error selecting QRPH: {e}")
        return False

# ═══════════════════════════════════════════════════════════════
# MAIN BOOKING FUNCTION
# ═══════════════════════════════════════════════════════════════
def do_booking(trigger_data):
    """Execute the full booking process"""
    
    date = trigger_data.get('date')
    slots = trigger_data.get('slots', [])
    
    if not date or not slots:
        send_telegram_message("❌ Invalid trigger data")
        return
    
    send_telegram_message(
        f"🚀 <b>BOOKING STARTED!</b>\n\n"
        f"📅 Date: {date}\n"
        f"🎯 Target: Up to {MAX_COURTS_TO_BOOK} court(s)"
    )
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            print("Opening booking page...")
            page.goto("https://app.onda.fit/book/thirsty-pickle", timeout=60000)
            page.wait_for_load_state("networkidle", timeout=60000)
            print("✓ Page loaded successfully!")
            
            # ═══════════════════════════════════════════════════════════
            # COURT NAMES MAPPING
            # ═══════════════════════════════════════════════════════════
            court_names = {
                "c8c8fb0a-518e-4838-b006-8f200e477788": "Court 1",
                "df1a98c3-deb2-4721-949a-d5a1e54fdce0": "Court 2",
                "0e853a91-33b6-4de2-9237-778007a9313b": "Court 3",
                "2166184c-db40-4a04-9a80-656878f7327b": "Court 4",
                "1cdcd209-71ce-4a72-a2f6-9252c4d06a01": "Court 5",
                "7aa7d361-9e60-433f-85ed-9e8eeaef8f96": "Court 6",
                "648d72bb-0789-40c6-9557-66709da121ba": "Court 7"
            }
            
            # ═══════════════════════════════════════════════════════════
            # TIME SLOTS: Evening (6 PM - 12 AM)
            # ═══════════════════════════════════════════════════════════
            target_times = ["18:00", "19:00", "20:00", "21:00", "22:00", "23:00"]
            time_display = {
                "18:00": "6 PM to 7 PM",
                "19:00": "7 PM to 8 PM",
                "20:00": "8 PM to 9 PM",
                "21:00": "9 PM to 10 PM",
                "22:00": "10 PM to 11 PM",
                "23:00": "11 PM to 12 AM"
            }
            
            # ═══════════════════════════════════════════════════════════
            # CHECK AVAILABILITY VIA API
            # ═══════════════════════════════════════════════════════════
            date_api = datetime.strptime(date, "%m/%d/%Y").strftime("%Y-%m-%d")
            print(f"Kumukuha ng availability para sa {date_api}...")
            data = get_availability(page, date_api)
            available_slots = get_all_available_slots(data, target_times, time_display, court_names)
            
            if not available_slots:
                send_telegram_message(f"❌ No available slots for {date}")
                browser.close()
                return
            
            print(f"\n  ✓✓✓ FOUND {len(available_slots)} AVAILABLE SLOTS!")
            for slot in available_slots:
                print(f"    - {slot['court']} @ {slot['display']}")
            
            # ═══════════════════════════════════════════════════════════
            # PUMILI NG SLOTS - MAX 2
            # ═══════════════════════════════════════════════════════════
            slots_to_book = []
            court_names_booked = []
            
            for slot in available_slots:
                if len(slots_to_book) < MAX_COURTS_TO_BOOK:
                    is_duplicate = False
                    for existing in slots_to_book:
                        if existing['court'] == slot['court'] and existing['display'] == slot['display']:
                            is_duplicate = True
                            break
                    
                    if not is_duplicate:
                        slots_to_book.append(slot)
                        court_names_booked.append(slot['court'])
            
            if len(slots_to_book) >= MAX_COURTS_TO_BOOK:
                send_telegram_message(
                    f"✅ Found {len(slots_to_book)} courts!\n"
                    f"📋 Booking: {', '.join(court_names_booked)}"
                )
            elif len(slots_to_book) == 1:
                send_telegram_message(
                    f"⚠️ Only 1 court available.\n"
                    f"📋 Booking: {slots_to_book[0]['court']} @ {slots_to_book[0]['display']}"
                )
            else:
                send_telegram_message("❌ No available slots found!")
                browser.close()
                return
            
            # ═══════════════════════════════════════════════════════════
            # SELECT ALL SLOTS SABAY (BAGO MAG PROCEED)
            # ═══════════════════════════════════════════════════════════
            if not select_multiple_slots(page, slots_to_book, date):
                send_telegram_message("❌ Failed to select slots!")
                browser.close()
                return
            
            take_screenshot(page, "step1_all_slots_selected.png")
            
            # ═══════════════════════════════════════════════════════════
            # PROCEED TO BOOKING
            # ═══════════════════════════════════════════════════════════
            print(f"\n[STEP 2] Clicking Proceed...")
            if not click_proceed_after_select(page):
                send_telegram_message("❌ Failed to click Proceed")
                browser.close()
                return
            
            page.wait_for_timeout(2000)
            take_screenshot(page, "step2_after_proceed.png")
            
            # ═══════════════════════════════════════════════════════════
            # FILL FORM
            # ═══════════════════════════════════════════════════════════
            print(f"\n[STEP 3] Filling booking form...")
            name = "Kazy Yap"
            phone = "9213145574"
            email = "boss.0024.kazy@gmail.com"
            
            if not fill_booking_form(page, name, phone, email):
                send_telegram_message("❌ Failed to fill form")
                browser.close()
                return
            
            take_screenshot(page, "step3_form_filled.png")
            
            # ═══════════════════════════════════════════════════════════
            # CLICK FORM PROCEED
            # ═══════════════════════════════════════════════════════════
            print(f"\n[STEP 4] Clicking Proceed on form...")
            if not click_form_proceed(page):
                send_telegram_message("❌ Failed to click form Proceed")
                browser.close()
                return
            
            page.wait_for_timeout(2000)
            take_screenshot(page, "step4_after_form_proceed.png")
            
            # ═══════════════════════════════════════════════════════════
            # TERMS AND PAYMENT
            # ═══════════════════════════════════════════════════════════
            print(f"\n[STEP 5] Confirming booking...")
            if not click_terms_and_proceed(page):
                send_telegram_message("❌ Failed to proceed to payment")
                browser.close()
                return
            
            page.wait_for_timeout(3000)
            take_screenshot(page, "step5_payment_page.png")
            
            # ═══════════════════════════════════════════════════════════
            # QRPH PAYMENT
            # ═══════════════════════════════════════════════════════════
            print(f"\n[STEP 6] Selecting payment method...")
            if select_qrph_payment(page):
                print("\n✓✓✓✓✓ ALL BOOKINGS COMPLETE!")
                court_list = "\n".join([f"  • {s['court']} @ {s['display']}" for s in slots_to_book])
                send_telegram_message(
                    f"✅ <b>ALL BOOKINGS COMPLETE!</b>\n\n"
                    f"📅 {date}\n"
                    f"📋 Booked {len(slots_to_book)} court(s):\n"
                    f"{court_list}\n\n"
                    f"💳 QR code has been sent! Please complete payment within 15 minutes."
                )
            else:
                send_telegram_message("❌ Failed to select QRPH payment method")
            
        except Exception as e:
            error_msg = f"❌ ERROR: {str(e)}"
            print(error_msg)
            send_telegram_message(error_msg)
            try:
                screenshot = page.screenshot(full_page=False)
                send_telegram_photo(screenshot, "Error screenshot")
            except:
                pass
        
        browser.close()

# ═══════════════════════════════════════════════════════════════
# FLASK WEBHOOK ENDPOINTS
# ═══════════════════════════════════════════════════════════════
@app.route('/trigger', methods=['POST'])
def trigger():
    """Receive trigger from Google Apps Script"""
    try:
        data = request.json
        print(f"📨 Trigger received: {data}")
        
        if not data.get('date') or not data.get('slots'):
            return jsonify({'status': 'error', 'message': 'Missing date or slots'}), 400
        
        thread = threading.Thread(target=do_booking, args=(data,))
        thread.daemon = True
        thread.start()
        
        return jsonify({'status': 'processing', 'message': 'Booking started'}), 200
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/')
def home():
    return "✅ Onda Booking Bot is running!"

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'}), 200

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
