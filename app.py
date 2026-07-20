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

TELEGRAM_BOT_TOKEN = "8911007553:AAHvDQCtA5R9yp2gQN-0irF6tPb-HjiOJ8k"
TELEGRAM_CHAT_ID = "-1004305386663"

MAX_COURTS_TO_BOOK = 2
BOOK_ANY_AVAILABLE = True

def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, data=data)
        print(f"✅ Telegram message sent to GC: {TELEGRAM_CHAT_ID}")
        return True
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return False

def send_telegram_photo(photo_bytes, caption=""):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        files = {'photo': ('screenshot.png', photo_bytes, 'image/png')}
        data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption}
        response = requests.post(url, files=files, data=data)
        print(f"✅ Telegram photo sent to GC: {TELEGRAM_CHAT_ID}")
        return True
    except Exception as e:
        print(f"❌ Telegram photo error: {e}")
        return False

def take_screenshot(page, filename="screenshot.png"):
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

def get_availability(page, date_api):
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
    try:
        court = slot['court']
        display = slot['display']
        print(f"  Selecting: {court} @ {display}")
        
        selector1 = f'button[aria-label="{court}: Mango Wing {display} available"]'
        btn = page.locator(selector1).first
        if btn.count() > 0:
            try:
                btn.click(timeout=3000)
                page.wait_for_timeout(500)
                print(f"    ✓ Selected! (Method 1)")
                return True
            except Exception as e:
                print(f"    ⚠️ Click failed: {e}")
        
        selector2 = f'button[aria-label*="{court}"][aria-label*="{display}"][aria-label*="available"]'
        btn = page.locator(selector2).first
        if btn.count() > 0:
            try:
                btn.click(timeout=3000)
                page.wait_for_timeout(500)
                print(f"    ✓ Selected! (Method 2)")
                return True
            except Exception as e:
                print(f"    ⚠️ Click failed: {e}")
        
        selector3 = f'button[aria-label*="{court}"][aria-label*="available"]'
        btn = page.locator(selector3).first
        if btn.count() > 0:
            try:
                aria_label = btn.get_attribute('aria-label')
                if display in aria_label:
                    btn.click(timeout=3000)
                    page.wait_for_timeout(500)
                    print(f"    ✓ Selected! (Method 3)")
                    return True
            except Exception as e:
                print(f"    ⚠️ Click failed: {e}")
        
        selector4 = f'button[aria-label*="available"]'
        btns = page.locator(selector4).all()
        for b in btns:
            try:
                aria_label = b.get_attribute('aria-label')
                if aria_label and court in aria_label and display in aria_label:
                    b.click(timeout=3000)
                    page.wait_for_timeout(500)
                    print(f"    ✓ Selected! (Method 4)")
                    return True
            except:
                pass
        
        selector5 = f'button[aria-label*="{court}"]'
        btns = page.locator(selector5).all()
        for b in btns:
            try:
                aria_label = b.get_attribute('aria-label')
                if aria_label and "available" in aria_label:
                    b.click(timeout=3000)
                    page.wait_for_timeout(500)
                    print(f"    ✓ Selected! (Method 5)")
                    return True
            except:
                pass
        
        print(f"    ✗ Cannot find button for {court} @ {display}")
        
        try:
            screenshot = page.screenshot(full_page=False)
            send_telegram_photo(screenshot, f"🔍 Cannot find {court} @ {display}")
        except:
            pass
        
        return False
        
    except Exception as e:
        print(f"    ✗ Error: {e}")
        return False

def click_proceed_after_select(page):
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
    try:
        print("  Waiting 2 seconds before clicking Terms checkbox...")
        time.sleep(2)
        
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
                f"✅ QR CODE READY!\n\nPlease scan to complete payment."
            )
            
            return True
        else:
            print("✗ QRPH payment option not found")
            return False
    except Exception as e:
        print(f"✗ Error selecting QRPH: {e}")
        return False

def do_booking(trigger_data):
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
            court_names = {
                "c8c8fb0a-518e-4838-b006-8f200e477788": "Court 1",
                "df1a98c3-deb2-4721-949a-d5a1e54fdce0": "Court 2",
                "0e853a91-33b6-4de2-9237-778007a9313b": "Court 3",
                "2166184c-db40-4a04-9a80-656878f7327b": "Court 4",
                "1cdcd209-71ce-4a72-a2f6-9252c4d06a01": "Court 5",
                "7aa7d361-9e60-433f-85ed-9e8eeaef8f96": "Court 6",
                "648d72bb-0789-40c6-9557-66709da121ba": "Court 7"
            }
            
            target_times = ["18:00", "19:00", "20:00", "21:00", "22:00", "23:00"]
            time_display = {
                "18:00": "6 PM to 7 PM",
                "19:00": "7 PM to 8 PM",
                "20:00": "8 PM to 9 PM",
                "21:00": "9 PM to 10 PM",
                "22:00": "10 PM to 11 PM",
                "23:00": "11 PM to 12 AM"
            }
            
            print("Opening booking page...")
            page.goto("https://app.onda.fit/book/thirsty-pickle", timeout=60000)
            page.wait_for_load_state("networkidle", timeout=60000)
            print("✓ Page loaded successfully!")
            
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
            
            booked_slots = []
            
            for idx, selected_slot in enumerate(slots_to_book, 1):
                print(f"\n{'='*50}")
                print(f"📌 BOOKING #{idx}: {selected_slot['court']} @ {selected_slot['display']}")
                print('='*50)
                
                try:
                    page.get_by_label("Select booking date").click()
                    page.wait_for_timeout(1000)
                    date_btn = page.locator(f'button[data-day="{date}"]').first
                    if date_btn.count() > 0 and not date_btn.is_disabled():
                        date_btn.click()
                        page.wait_for_timeout(1500)
                    else:
                        print("⚠️ Date button not found, reloading page...")
                        page.goto("https://app.onda.fit/book/thirsty-pickle", timeout=60000)
                        page.wait_for_load_state("networkidle", timeout=60000)
                        page.get_by_label("Select booking date").click()
                        page.wait_for_timeout(1000)
                        date_btn = page.locator(f'button[data-day="{date}"]').first
                        if date_btn.count() > 0 and not date_btn.is_disabled():
                            date_btn.click()
                            page.wait_for_timeout(1500)
                except Exception as e:
                    print(f"⚠️ Error selecting date: {e}")
                    page.goto("https://app.onda.fit/book/thirsty-pickle", timeout=60000)
                    page.wait_for_load_state("networkidle", timeout=60000)
                    page.get_by_label("Select booking date").click()
                    page.wait_for_timeout(1000)
                    date_btn = page.locator(f'button[data-day="{date}"]').first
                    if date_btn.count() > 0 and not date_btn.is_disabled():
                        date_btn.click()
                        page.wait_for_timeout(1500)
                
                print(f"\n[STEP 1] Selecting slot...")
                success = False
                
                for attempt in range(3):
                    if select_slot(page, selected_slot):
                        print("✓ Slot selected!")
                        page.wait_for_timeout(1000)
                        success = True
                        break
                    else:
                        print(f"⚠️ Attempt {attempt + 1} failed, retrying...")
                        page.wait_for_timeout(1000)
                        try:
                            page.get_by_label("Select booking date").click()
                            page.wait_for_timeout(1000)
                            date_btn = page.locator(f'button[data-day="{date}"]').first
                            if date_btn.count() > 0 and not date_btn.is_disabled():
                                date_btn.click()
                                page.wait_for_timeout(1500)
                        except:
                            pass
                
                if not success:
                    print(f"✗ {selected_slot['court']} is no longer available!")
                    send_telegram_message(f"⚠️ {selected_slot['court']} @ {selected_slot['display']} is no longer available!")
                    
                    print("🔍 Looking for alternative court...")
                    
                    date_api = datetime.strptime(date, "%m/%d/%Y").strftime("%Y-%m-%d")
                    data = get_availability(page, date_api)
                    available_slots = get_all_available_slots(data, target_times, time_display, court_names)
                    
                    booked_courts = [s['court'] for s in booked_slots]
                    available_slots = [s for s in available_slots if s['court'] not in booked_courts]
                    
                    if available_slots:
                        alternative_slot = available_slots[0]
                        print(f"✅ Found alternative: {alternative_slot['court']} @ {alternative_slot['display']}")
                        send_telegram_message(
                            f"🔄 Found alternative court!\n"
                            f"📋 Booking: {alternative_slot['court']} @ {alternative_slot['display']}"
                        )
                        
                        print(f"\n[STEP 1 RETRY] Selecting alternative slot...")
                        alt_success = False
                        for attempt in range(3):
                            if select_slot(page, alternative_slot):
                                print("✓ Alternative slot selected!")
                                page.wait_for_timeout(1000)
                                alt_success = True
                                break
                            else:
                                print(f"⚠️ Alternative attempt {attempt + 1} failed, retrying...")
                                page.wait_for_timeout(1000)
                        
                        if alt_success:
                            selected_slot = alternative_slot
                            success = True
                        else:
                            send_telegram_message(f"❌ Alternative slot also unavailable!")
                            continue
                    else:
                        send_telegram_message(f"❌ No alternative slots available!")
                        continue
                
                if not success:
                    continue
                
                take_screenshot(page, f"step1_slot_selected_{idx}.png")
                
                print(f"\n[STEP 2] Clicking Proceed...")
                if click_proceed_after_select(page):
                    print("✓ Proceed clicked!")
                    page.wait_for_timeout(2000)
                    
                    take_screenshot(page, f"step2_after_proceed_{idx}.png")
                    
                    print(f"\n[STEP 3] Filling booking form...")
                    name = "Kazy Yap"
                    phone = "9213145574"
                    email = "boss.0024.kazy@gmail.com"
                    
                    if fill_booking_form(page, name, phone, email):
                        print("✓ Form filled!")
                        page.wait_for_timeout(500)
                        
                        take_screenshot(page, f"step3_form_filled_{idx}.png")
                        
                        print(f"\n[STEP 4] Clicking Proceed on form...")
                        if click_form_proceed(page):
                            print("✓ Form Proceed clicked!")
                            page.wait_for_timeout(2000)
                            
                            take_screenshot(page, f"step4_after_form_proceed_{idx}.png")
                            
                            print(f"\n[STEP 5] Confirming booking...")
                            if click_terms_and_proceed(page):
                                print("✓ Confirm & Proceed to Payment clicked!")
                                page.wait_for_timeout(3000)
                                
                                take_screenshot(page, f"step5_payment_page_{idx}.png")
                                
                                print(f"\n[STEP 6] Selecting payment method...")
                                if select_qrph_payment(page):
                                    print(f"\n✓✓✓✓✓ BOOKING #{idx} COMPLETE!")
                                    print(f"Booked: {selected_slot['court']} on {date} at {selected_slot['display']}")
                                    
                                    booked_slots.append(selected_slot)
                                    
                                    send_telegram_message(
                                        f"✅ <b>BOOKING #{idx} COMPLETE!</b>\n\n"
                                        f"📅 {date}\n"
                                        f"🎯 {selected_slot['court']} @ {selected_slot['display']}\n\n"
                                        f"💳 QR code sent! Please complete payment within 15 minutes."
                                    )
                                else:
                                    print(f"\n✗ Failed to select QRPH payment method for #{idx}")
                                    send_telegram_message(f"❌ Failed to select QRPH payment for {selected_slot['court']}")
                            else:
                                print(f"\n✗ Failed to proceed to payment for #{idx}")
                                send_telegram_message(f"❌ Failed to proceed to payment for {selected_slot['court']}")
                        else:
                            print(f"\n✗ Failed to click form Proceed for #{idx}")
                            send_telegram_message(f"❌ Failed to click form Proceed for {selected_slot['court']}")
                    else:
                        print(f"\n✗ Failed to fill form for #{idx}")
                        send_telegram_message(f"❌ Failed to fill form for {selected_slot['court']}")
                else:
                    print(f"\n✗ Failed to click Proceed for #{idx}")
                    send_telegram_message(f"❌ Failed to click Proceed for {selected_slot['court']}")
                
                if idx < len(slots_to_book):
                    print(f"\n🔄 Returning to booking page for next court...")
                    page.goto("https://app.onda.fit/book/thirsty-pickle", timeout=60000)
                    page.wait_for_load_state("networkidle", timeout=60000)
                    time.sleep(2)
            
            if booked_slots:
                court_list = "\n".join([f"  • {s['court']} @ {s['display']}" for s in booked_slots])
                send_telegram_message(
                    f"🎉 <b>ALL BOOKINGS COMPLETE!</b>\n\n"
                    f"📅 {date}\n"
                    f"📋 Booked {len(booked_slots)} court(s):\n"
                    f"{court_list}\n\n"
                    f"💳 Check each booking for QR code."
                )
            else:
                send_telegram_message("❌ No bookings were successful!")
            
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

@app.route('/trigger', methods=['POST', 'GET'])
def trigger():
    if request.method == 'GET':
        return jsonify({
            'status': 'ok', 
            'message': 'Webhook is running. Send POST request with date and slots.'
        }), 200
    
    try:
        data = None
        
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()
        
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except:
                pass
        
        print(f"📨 Trigger received: {data}")
        print(f"📨 Request method: {request.method}")
        print(f"📨 Request data: {request.data}")
        print(f"📨 Request form: {request.form}")
        
        if not data:
            return jsonify({
                'status': 'error', 
                'message': 'No data received'
            }), 400
        
        if not data.get('date') or not data.get('slots'):
            return jsonify({
                'status': 'error', 
                'message': f'Missing date or slots. Received: {data}'
            }), 400
        
        thread = threading.Thread(target=do_booking, args=(data,))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'status': 'processing', 
            'message': 'Booking started',
            'received': data
        }), 200
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({
            'status': 'error', 
            'message': str(e)
        }), 500

@app.route('/')
def home():
    return "✅ Onda Booking Bot is running!"

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'}), 200

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
