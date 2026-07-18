# app.py - Full Onda Booking Bot with Webhook + Telegram
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
TELEGRAM_CHAT_ID = "-5427084407"        # ← Chat ID mo

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
        
        # Send to Telegram
        send_telegram_photo(screenshot_bytes, "📸 Booking progress screenshot")
        
        # Also save locally (for debugging)
        with open(filename, "wb") as f:
            f.write(screenshot_bytes)
        
        print(f"✅ Screenshot saved: {filename}")
        return screenshot_bytes
    except Exception as e:
        print(f"❌ Failed to take screenshot: {e}")
        return None

# ═══════════════════════════════════════════════════════════════
# BOOKING FUNCTIONS - FROM YOUR ORIGINAL ball.py
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

def select_slot(page, slot):
    """Pumili ng isang slot sa UI"""
    try:
        selector = f'button[aria-label*="{slot["court"]}"][aria-label*="{slot["display"]}"][aria-label*="available"]'
        print(f"  Selecting: {slot['court']} @ {slot['display']}")
        
        btn = page.locator(selector).first
        if btn.count() > 0:
            btn.click()
            page.wait_for_timeout(500)
            print(f"    ✓ Selected!")
            return True
        else:
            print(f"    ✗ Cannot find button")
            return False
    except Exception as e:
        print(f"    ✗ Error: {e}")
        return False

def click_proceed_after_select(page):
    """Hanapin at i-click ang Proceed button pagkatapos pumili ng court"""
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
        else:
            print("✗ Cannot find Full Name input")
        
        page.wait_for_timeout(500)
        
        print("Filling Phone Number...")
        phone_input = page.locator('input[aria-label="Phone Number"]').first
        if phone_input.count() > 0:
            phone_input.click()
            phone_input.fill("")
            phone_input.fill(phone)
            print(f"✓ Phone filled: {phone}")
        else:
            print("✗ Cannot find Phone Number input")
            phone_input_alt = page.locator('input[type="tel"]').first
            if phone_input_alt.count() > 0:
                phone_input_alt.click()
                phone_input_alt.fill("")
                phone_input_alt.fill(phone)
                print(f"✓ Phone filled (alternative): {phone}")
        
        page.wait_for_timeout(500)
        
        print("Filling Email Address...")
        email_input = page.locator('input[aria-label="Email Address"]').first
        if email_input.count() > 0:
            email_input.click()
            email_input.fill("")
            email_input.fill(email)
            print(f"✓ Email filled: {email}")
        else:
            print("✗ Cannot find Email Address input")
            email_input_alt = page.locator('input[type="email"]').first
            if email_input_alt.count() > 0:
                email_input_alt.click()
                email_input_alt.fill("")
                email_input_alt.fill(email)
                print(f"✓ Email filled (alternative): {email}")
        
        page.wait_for_timeout(500)
        
        print("  Waiting 3 seconds before clicking Proceed...")
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
        wait_time = 2
        print(f"  Waiting {wait_time} seconds before clicking Terms checkbox...")
        time.sleep(wait_time)
        
        print("Clicking Terms checkbox...")
        terms_checkbox = page.locator('input[id="terms-accepted"]').first
        if terms_checkbox.count() > 0:
            terms_checkbox.click()
            print("✓ Terms checkbox clicked!")
        else:
            print("✗ Cannot find Terms checkbox")
        
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
            
            # 🔥 TAKE SCREENSHOT OF QR CODE
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

def open_calendar(page):
    """Buksan ang calendar"""
    try:
        print("Opening calendar...")
        page.get_by_label("Select booking date").click(timeout=30000)
        page.wait_for_timeout(1500)
        print("✓ Calendar opened!")
        return True
    except Exception as e:
        print(f"✗ Error opening calendar: {e}")
        return False

# ═══════════════════════════════════════════════════════════════
# MAIN BOOKING FUNCTION - TRIGGERED VIA WEBHOOK
# ═══════════════════════════════════════════════════════════════
def do_booking(trigger_data):
    """Execute the full booking process from ball.py"""
    
    date = trigger_data.get('date')
    slots = trigger_data.get('slots', [])
    
    if not date or not slots:
        send_telegram_message("❌ Invalid trigger data")
        return
    
    selected_slot = slots[0]
    
    # Send Telegram notification
    send_telegram_message(
        f"🚀 <b>BOOKING STARTED!</b>\n\n"
        f"📅 Date: {date}\n"
        f"🎯 Slot: {selected_slot['court']} @ {selected_slot['display']}"
    )
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)  # Headless for cloud
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
            # SELECT THE DATE
            # ═══════════════════════════════════════════════════════════
            print(f"\nSelecting date: {date}")
            page.get_by_label("Select booking date").click()
            page.wait_for_timeout(1500)
            print("✓ Calendar opened!")
            
            date_btn = page.locator(f'button[data-day="{date}"]').first
            
            if date_btn.count() > 0:
                is_disabled = date_btn.is_disabled()
                if not is_disabled:
                    date_btn.click()
                    print(f"✓ Clicked date: {date}")
                    page.wait_for_timeout(1500)
                else:
                    send_telegram_message(f"❌ Date {date} is DISABLED")
                    browser.close()
                    return
            else:
                send_telegram_message(f"❌ Date {date} not found in calendar")
                browser.close()
                return
            
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
            
            # Use the selected slot from trigger
            # Find matching slot or use first available
            matching_slot = None
            for slot in available_slots:
                if slot['court'] == selected_slot['court'] and slot['display'] == selected_slot['display']:
                    matching_slot = slot
                    break
            
            if not matching_slot:
                matching_slot = available_slots[0]
                send_telegram_message(
                    f"⚠️ Selected slot not available. Using: {matching_slot['court']} @ {matching_slot['display']}"
                )
            
            # ═══════════════════════════════════════════════════════════
            # BOOKING STEPS - FROM YOUR ORIGINAL ball.py
            # ═══════════════════════════════════════════════════════════
            print(f"\n{'='*50}")
            print(f"✓✓✓ BOOKING: {date} - {matching_slot['court']} @ {matching_slot['display']}")
            print('='*50)
            
            # STEP 1: Select slot
            print(f"\n[STEP 1] Selecting slot...")
            if select_slot(page, matching_slot):
                print("✓ Slot selected!")
                page.wait_for_timeout(1000)
                
                # Take screenshot
                take_screenshot(page, "step1_slot_selected.png")
                
                # STEP 2: Click Proceed
                print(f"\n[STEP 2] Clicking Proceed...")
                if click_proceed_after_select(page):
                    print("✓ Proceed clicked!")
                    page.wait_for_timeout(2000)
                    
                    # Take screenshot
                    take_screenshot(page, "step2_after_proceed.png")
                    
                    # STEP 3: Fill form
                    print(f"\n[STEP 3] Filling booking form...")
                    name = "Delfin C. Carlos Jr."
                    phone = "9213145574"
                    email = "delfincarlos2828@gmail.com"
                    
                    if fill_booking_form(page, name, phone, email):
                        print("✓ Form filled!")
                        page.wait_for_timeout(500)
                        
                        # Take screenshot
                        take_screenshot(page, "step3_form_filled.png")
                        
                        # STEP 4: Click Proceed on form
                        print(f"\n[STEP 4] Clicking Proceed on form...")
                        if click_form_proceed(page):
                            print("✓ Form Proceed clicked!")
                            page.wait_for_timeout(2000)
                            
                            # Take screenshot
                            take_screenshot(page, "step4_after_form_proceed.png")
                            
                            # STEP 5: Terms and Proceed to Payment
                            print(f"\n[STEP 5] Confirming booking...")
                            if click_terms_and_proceed(page):
                                print("✓ Confirm & Proceed to Payment clicked!")
                                page.wait_for_timeout(3000)
                                
                                # Take screenshot
                                take_screenshot(page, "step5_payment_page.png")
                                
                                # STEP 6: Select QRPH payment
                                print(f"\n[STEP 6] Selecting payment method...")
                                if select_qrph_payment(page):
                                    print("\n✓✓✓✓✓ BOOKING COMPLETE!")
                                    print(f"Booked: {matching_slot['court']} on {date} at {matching_slot['display']}")
                                    print("✓ QRPH payment method selected - QR code should be displayed!")
                                    
                                    send_telegram_message(
                                        f"✅ <b>BOOKING COMPLETE!</b>\n\n"
                                        f"📅 {date}\n"
                                        f"🎯 {matching_slot['court']} @ {matching_slot['display']}\n\n"
                                        f"💳 QR code has been sent! Please complete payment within 15 minutes."
                                    )
                                else:
                                    print("\n✗ Failed to select QRPH payment method")
                                    send_telegram_message("❌ Failed to select QRPH payment method")
                            else:
                                print("\n✗ Failed to proceed to payment")
                                send_telegram_message("❌ Failed to proceed to payment")
                        else:
                            print("\n✗ Failed to click form Proceed")
                            send_telegram_message("❌ Failed to click form Proceed")
                    else:
                        print("\n✗ Failed to fill form")
                        send_telegram_message("❌ Failed to fill form")
                else:
                    print("\n✗ Failed to click Proceed")
                    send_telegram_message("❌ Failed to click Proceed")
            else:
                print("\n✗ Failed to select slot")
                send_telegram_message("❌ Failed to select slot")
            
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
        
        # Validate data
        if not data.get('date') or not data.get('slots'):
            return jsonify({'status': 'error', 'message': 'Missing date or slots'}), 400
        
        # Run booking in background
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
