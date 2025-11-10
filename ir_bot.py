import telebot
import json
import os
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ForceReply
import pandas as pd
from datetime import datetime
import io
from openpyxl.styles import PatternFill
from cryptography.fernet import Fernet
import base64
import atexit

# === FIX RENDER/RAILWAY PATH + PERSISTENT DISK ===
if os.path.exists('/data'):  # Render Disk
    os.chdir('/data')
else:
    os.makedirs('/opt/render/project/src/data', exist_ok=True)
    os.chdir('/opt/render/project/src/data')

# === TOKEN + KEY ===
TOKEN = os.getenv('BOT_TOKEN')
ENCRYPT_KEY = os.getenv('ENCRYPT_KEY')
if not ENCRYPT_KEY:
    ENCRYPT_KEY = base64.urlsafe_b64encode(os.urandom(32)).decode()
    print(f"\n=== ENCRYPT_KEY MỚI (COPY DÁN VÀO VARIABLES NGAY): ===\n{ENCRYPT_KEY}\n")

cipher = Fernet(ENCRYPT_KEY.encode())
bot = telebot.TeleBot(TOKEN)

# === WHITELIST USER (THAY ID CỦA BẠN) ===
ALLOWED_USERS = [6796774010]  # ← ID bạn đã đúng

DATA_FILE = 'data.enc'
tasks = {}
user_states = {}

# === MÃ HÓA / GIẢI MÃ ===
def load_encrypted():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'rb') as f:
                data = json.loads(cipher.decrypt(f.read()).decode('utf-8'))
            return data.get("tasks", {})
        except:
            return {}
    return {}

def save_encrypted():
    data = json.dumps({"tasks": tasks}, ensure_ascii=False)
    with open(DATA_FILE, 'wb') as f:
        f.write(cipher.encrypt(data.encode('utf-8')))

tasks = load_encrypted()
atexit.register(save_encrypted)

# === BẢO MẬT ===
def is_allowed(user_id):
    return user_id in ALLOWED_USERS

def protected(func):
    def wrapper(message):
        if not is_allowed(message.from_user.id):
            bot.reply_to(message, "❌ Bạn không có quyền dùng bot này!")
            return
        func(message)
    return wrapper

# === DỮ LIỆU ===
REQUIRED_FIELDS = ["service_request","response_plan","ir_report","attack_map","list_evidence","up_log","lesson_learned"]
FIELDS_ORDER = ["irid","khach_hang","nguoi_thuc_hien","created","updated","incident_info"] + REQUIRED_FIELDS + ["status"]

def main_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    markup.add('/add', '/list', '/thieu')
    markup.add('/ir', '/done', '/thongke')
    markup.add('/export', '/cancel')
    return markup

# === /START ===
@bot.message_handler(commands=['start'])
@protected
def start(message):
    chat_id = str(message.chat.id)
    tasks.setdefault(chat_id, [])
    bot.reply_to(message,
                 "🛡️ *BOT QUẢN LÝ IR - KHÔNG BỎ SÓT 7 MỤC!*\n\n"
                 "Lệnh:\n"
                 "/add - Thêm IR mới\n"
                 "/list - Xem tất cả\n"
                 "/ir 12345 - Xem chi tiết\n"
                 "/thieu - IR còn ND\n"
                 "/done 12345 - Đánh dấu Done\n"
                 "/thongke - Thống kê\n"
                 "/export - Excel (ô đỏ = ND)",
                 parse_mode='Markdown', reply_markup=main_keyboard())

# === /CANCEL ===
@bot.message_handler(commands=['cancel'])
@protected
def cancel_operation(message):
    user_id = str(message.chat.id)
    if user_id in user_states:
        del user_states[user_id]
    bot.reply_to(message, "❌ *Đã hủy thao tác!* Quay lại menu ✅", parse_mode='Markdown', reply_markup=main_keyboard())

# === /ADD ===
@bot.message_handler(commands=['add'])
@protected
def start_add(message):
    user_id = str(message.chat.id)
    user_states[user_id] = {'mode': 'add', 'step': 0, 'data': {}}
    send_prompt(user_id, 0)

def send_prompt(user_id, step):
    field = FIELDS_ORDER[step]
    prompt = f"➕ *Thêm IR mới* [{step+1}/{len(FIELDS_ORDER)}]\n\n📌 Nhập *{field.replace('_', ' ').title()}*:"
    if field in ["created", "updated"]:
        prompt += "\n(dd/mm/yyyy hoặc n/a)"
    elif field in REQUIRED_FIELDS:
        prompt += "\n(D = Done ✅ | ND = Not Done ❌)"
    elif field == "status":
        prompt += "\n(backlog | in progress | post incident | done)"
    prompt += "\n\n/cancel để thoát"
    bot.send_message(user_id, prompt, parse_mode='Markdown', reply_markup=ForceReply())

@bot.message_handler(func=lambda m: str(m.chat.id) in user_states and user_states[str(m.chat.id)].get('mode') == 'add')
@protected
def handle_add_steps(message):
    user_id = str(message.chat.id)
    if message.text and message.text.strip().lower() == "/cancel":
        cancel_operation(message)
        return
    state = user_states[user_id]
    step = state['step']
    field = FIELDS_ORDER[step]
    text = message.text.strip()
    chat_id = user_id
    tasks.setdefault(chat_id, [])

    if field == "irid":
        if not text.isdigit():
            bot.reply_to(message, "❌ IRID phải là số!")
            return
        if any(ir['irid'] == text for ir in tasks[chat_id]):
            bot.reply_to(message, "❌ IRID đã tồn tại!")
            return
        state['data']['irid'] = text
    elif field == "created":
        if not validate_date(text):
            bot.reply_to(message, "❌ Sai định dạng ngày! (dd/mm/yyyy)")
            return
        state['data']['created'] = text
    elif field == "updated":
        state['data']['updated'] = text if text.lower() != "n/a" else "n/a"
    elif field == "incident_info":
        state['data']['incident_info'] = text
    elif field in REQUIRED_FIELDS:
        if text.upper() not in ["D", "ND"]:
            bot.reply_to(message, "❌ Chỉ nhập D hoặc ND!")
            return
        state['data'][field] = "✅ Done" if text.upper() == "D" else "❌ Not Done"
    elif field == "status":
        valid = ["backlog", "in progress", "post incident", "done"]
        if text.lower() not in valid:
            bot.reply_to(message, f"❌ Chỉ nhập: {', '.join(valid)}")
            return
        state['data']['status'] = text.lower()
    else:
        state['data'][field] = text

    if step + 1 < len(FIELDS_ORDER):
        state['step'] += 1
        send_prompt(user_id, state['step'])
    else:
        tasks[chat_id].append(state['data'])
        save_encrypted()
        del user_states[user_id]
        ir = state['data']
        missing = [f for f in REQUIRED_FIELDS if ir.get(f) == "❌ Not Done"]
        bot.reply_to(message,
                     f"✅ *IR {ir['irid']} tạo thành công!*\n"
                     f"{'🎉 Hoàn thành 100%!' if not missing else f'⚠️ Còn {len(missing)} mục ND'}\n\n"
                     f"🏢 {ir['khach_hang']} | 👤 {ir['nguoi_thuc_hien']}\n"
                     f"📅 {ir['created']} | Status: {ir['status'].title()}",
                     parse_mode='Markdown', reply_markup=main_keyboard())
        show_ir_detail(chat_id, ir)

def validate_date(d):
    if not d or d.lower() == "n/a": return True
    try:
        datetime.strptime(d, "%d/%m/%Y")
        return True
    except:
        return False

def format_field(f):
    return f.replace("_", " ").title()

def find_ir(chat_id, irid):
    for ir in tasks.get(str(chat_id), []):
        if ir['irid'] == irid:
            return ir
    return None

def show_ir_detail(chat_id, ir):
    status_emoji = {"backlog": "🔴", "in progress": "🟡", "post incident": "🟠", "done": "🟢"}.get(ir['status'], "⚪")
    msg = f"🔍 *IR {ir['irid']} - {ir['khach_hang']}*\n"
    msg += f"👤 Người: `{ir['nguoi_thuc_hien']}`\n"
    msg += f"📅 Tạo: `{ir['created']}` | Cập nhật: `{ir['updated']}`\n"
    msg += f"⚠️ Incident Info: {ir['incident_info']}\n"
    msg += f"📊 Status: {status_emoji} `{ir['status'].title()}`\n\n"
    msg += "*7 Mục bắt buộc:*\n"
    for f in REQUIRED_FIELDS:
        status = ir.get(f, "❌ Not Done")
        msg += f"┣ {format_field(f)}: {status}\n"
    missing = [f for f in REQUIRED_FIELDS if ir.get(f) == "❌ Not Done"]
    msg += f"\n{'🎉 Hoàn thành!' if not missing else f'🔴 Còn thiếu: {len(missing)} mục'}"
    bot.send_message(chat_id, msg, parse_mode='Markdown')

# === /IR ===
@bot.message_handler(commands=['ir'])
@protected
def view_ir(message):
    try:
        irid = message.text.split(maxsplit=1)[1]
        ir = find_ir(message.chat.id, irid)
        if ir:
            show_ir_detail(message.chat.id, ir)
        else:
            bot.reply_to(message, "❌ Không tìm thấy IR này!")
    except:
        bot.reply_to(message, "Dùng: /ir 642")

# === /DONE ===
@bot.message_handler(commands=['done'])
@protected
def start_mark_done(message):
    try:
        irid = message.text.split()[1]
        ir = find_ir(message.chat.id, irid)
        if not ir:
            bot.reply_to(message, "Không tìm thấy IR!")
            return
        missing = [f for f in REQUIRED_FIELDS if ir.get(f) == "❌ Not Done"]
        if not missing:
            bot.reply_to(message, "IR này đã hoàn thành!")
            return
        markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        for f in missing:
            markup.add(KeyboardButton(f"{irid} {f}"))
        markup.add("/cancel")
        bot.reply_to(message, f"Chọn mục đánh dấu DONE cho IR {irid}:", reply_markup=markup)
        user_states[str(message.chat.id)] = {'mode': 'done', 'irid': irid}
    except:
        bot.reply_to(message, "Dùng: /done 642")

@bot.message_handler(func=lambda m: str(m.chat.id) in user_states and user_states[str(m.chat.id)].get('mode') == 'done')
@protected
def process_done(message):
    if message.text.strip().lower() == "/cancel":
        cancel_operation(message)
        return
    user_id = str(message.chat.id)
    state = user_states[user_id]
    text = message.text.strip()
    if " " not in text: return
    selected_irid, field = text.split(" ", 1)
    if selected_irid != state['irid'] or field not in REQUIRED_FIELDS: return
    ir = find_ir(message.chat.id, selected_irid)
    if ir and ir.get(field) == "❌ Not Done":
        ir[field] = "✅ Done"
        ir['updated'] = datetime.now().strftime("%d/%m/%Y")
        save_encrypted()
        bot.reply_to(message, f"✅ Đã đánh dấu *{format_field(field)}* DONE!", parse_mode='Markdown', reply_markup=main_keyboard())
        show_ir_detail(message.chat.id, ir)
    del user_states[user_id]

# === /LIST ===
@bot.message_handler(commands=['list'])
@protected
def list_all(message):
    ir_list = tasks.get(str(message.chat.id), [])
    if not ir_list:
        bot.reply_to(message, "Chưa có IR nào!")
        return
    msg = f"📋 *Danh sách IR ({len(ir_list)})*\n\n"
    for ir in ir_list:
        missing = sum(1 for f in REQUIRED_FIELDS if ir.get(f) == "❌ Not Done")
        emoji = "✅" if missing == 0 else f"🔴{missing}"
        status_emoji = {"backlog": "🔴", "in progress": "🟡", "post incident": "🟠", "done": "🟢"}.get(ir['status'], "⚪")
        msg += f"• IR {ir['irid']} | {ir['khach_hang'][:15]} | {emoji} | {status_emoji} {ir['status'].title()}\n"
    bot.reply_to(message, msg, parse_mode='Markdown', reply_markup=main_keyboard())

# === /THIEU ===
@bot.message_handler(commands=['thieu'])
@protected
def ir_thieu(message):
    chat_id = str(message.chat.id)
    incomplete = [ir for ir in tasks.get(chat_id, []) if any(ir.get(f) == "❌ Not Done" for f in REQUIRED_FIELDS)]
    if not incomplete:
        bot.reply_to(message, "🎉 Tất cả IR đã hoàn thành 7 mục bắt buộc!")
        return
    msg = f"🔴 *IR còn thiếu ({len(incomplete)})*\n\n"
    for ir in incomplete:
        missing = [f for f in REQUIRED_FIELDS if ir.get(f) == "❌ Not Done"]
        msg += f"IR {ir['irid']} - {ir['khach_hang']} ({len(missing)} thiếu)\n"
    bot.reply_to(message, msg, parse_mode='Markdown', reply_markup=main_keyboard())

# === /THONGKE ===
@bot.message_handler(commands=['thongke'])
@protected
def thongke(message):
    ir_list = tasks.get(str(message.chat.id), [])
    total = len(ir_list)
    done_all = sum(1 for ir in ir_list if all(ir.get(f) == "✅ Done" for f in REQUIRED_FIELDS))
    backlog = sum(1 for ir in ir_list if ir['status'] == 'backlog')
    inprog = sum(1 for ir in ir_list if ir['status'] == 'in progress')
    post = sum(1 for ir in ir_list if ir['status'] == 'post incident')
    done = sum(1 for ir in ir_list if ir['status'] == 'done')
    msg = f"📊 *Thống kê IR*\n\n"
    msg += f"Tổng IR: {total}\n"
    msg += f"Hoàn thành 100%: {done_all}\n"
    msg += f"Tỷ lệ hoàn thành: {done_all/total*100 if total else 0:.1f}%\n\n"
    msg += f"🔴 Backlog: {backlog}\n"
    msg += f"🟡 In Progress: {inprog}\n"
    msg += f"🟠 Post Incident: {post}\n"
    msg += f"🟢 Done: {done}\n"
    bot.reply_to(message, msg, parse_mode='Markdown', reply_markup=main_keyboard())

# === /EXPORT ===
@bot.message_handler(commands=['export'])
@protected
def export_excel(message):
    chat_id = str(message.chat.id)
    ir_list = tasks.get(chat_id, [])
    if not ir_list:
        bot.reply_to(message, "Chưa có dữ liệu!")
        return
    df = pd.DataFrame(ir_list)
    cols = ['irid','khach_hang','nguoi_thuc_hien','created','updated','incident_info','status'] + REQUIRED_FIELDS
    df = df[cols]
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='IR Reports')
        worksheet = writer.sheets['IR Reports']
        red_fill = PatternFill(start_color='FFFF0000', end_color='FFFF0000', fill_type='solid')
        for row in range(2, len(ir_list) + 2):
            for col in range(8, 15):
                cell = worksheet.cell(row=row, column=col)
                if "Not Done" in str(cell.value):
                    cell.fill = red_fill
    output.seek(0)
    bot.send_document(chat_id, output,
                      caption=f"📊 IR Export - {datetime.now().strftime('%d/%m/%Y')}",
                      visible_file_name=f"IR_Report_{datetime.now().strftime('%Y%m%d')}.xlsx")

# === CHẠY BOT ===
print("IR BOT FULL - KHÔNG REMIND - CHẠY 24/7 TRÊN RENDER/RAILWAY - 10/11/2025")
bot.infinity_polling(skip_pending=True)
