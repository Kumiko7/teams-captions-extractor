import threading
import time
import re
import os
import datetime
import ctypes
import atexit  # Imported to handle termination saving
import uiautomation as auto
from flask import Flask, render_template_string, request
from flask_socketio import SocketIO

# ==========================================
# CONFIGURATION
# ==========================================
KEYWORDS = ["edwin", "エドウィン", "えどうぃん"]
PORT = 5000
LOG_FOLDER = "logs"
SEARCH_DEPTH = 60 
LOG_INTERVAL_SECONDS = 10  # Write to file every 10 seconds

# ==========================================
# SYSTEM HELPERS
# ==========================================
def get_process_name(pid):
    try:
        PROCESS_QUERY_INFORMATION = 0x0400
        PROCESS_VM_READ = 0x0010
        h_process = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not h_process: return ""
        buf = ctypes.create_unicode_buffer(1024)
        ctypes.windll.psapi.GetModuleBaseNameW(h_process, 0, buf, 1024)
        name = buf.value.lower()
        ctypes.windll.kernel32.CloseHandle(h_process)
        return name
    except:
        return ""

# ==========================================
# FILE LOGGING
# ==========================================
if not os.path.exists(LOG_FOLDER): os.makedirs(LOG_FOLDER)
current_time_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_filename = f"transcript_{current_time_str}.txt"
log_filepath = os.path.join(LOG_FOLDER, log_filename)
transcript_memory = {}

def update_log_file():
    """Writes the current transcript memory to disk."""
    try:
        with open(log_filepath, "w", encoding="utf-8") as f:
            f.write(f"Meeting Transcript - Started {current_time_str}\n")
            f.write("==================================================\n\n")
            for uid, data in transcript_memory.items():
                f.write(f"[{data.get('time')}] {data.get('speaker')}: {data.get('text')}\n")
        # print(f"💾 Log saved to {log_filename}") # Optional debug
    except Exception as e:
        print(f"Error saving log: {e}")

# Register the save function to run when script is terminated
atexit.register(update_log_file)

# ==========================================
# FLASK & SOCKET SETUP (FIXED)
# ==========================================
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

@socketio.on('connect')
def handle_connect():
    print(f"✅ Web Client Connected! (SID: {request.sid})")
    for uid, data in transcript_memory.items():
        socketio.emit('caption_update', {'id': uid, 'text': data['text'], 'speaker': data['speaker']}, to=request.sid)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Live Teams Transcripts</title>
    <style>
        body { font-family: 'Segoe UI', Meiryo, sans-serif; background-color: #202020; color: #fff; margin: 0; padding: 20px; }
        #container { max-width: 900px; margin: 0 auto; padding-bottom: 50px; }
        .caption-line { background-color: #333; margin-bottom: 10px; padding: 15px; border-radius: 8px; border-left: 4px solid #6264A7; }
        .speaker { font-size: 0.85em; color: #aaa; margin-bottom: 5px; font-weight: bold; }
        .text { font-size: 1.2em; line-height: 1.4em; }
        .highlight { color: #FF4444; font-weight: 900; background-color: rgba(50, 0, 0, 0.5); padding: 2px 4px; border-radius: 4px; border: 1px solid #ff4444; }
        #status { position: fixed; top: 0; left: 0; right: 0; background: #000; color: lime; padding: 5px; text-align: center; font-size: 0.8em; opacity: 0.8; z-index: 999; }
    </style>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
</head>
<body>
    <div id="status">Connecting to server...</div>
    <div id="container"></div>
    <script>
        const socket = io({transports: ['websocket', 'polling']});
        const container = document.getElementById('container');
        const status = document.getElementById('status');
        const keywords = {{ keywords | tojson }};

        function processText(text) {
            let processed = text;
            keywords.forEach(word => {
                const regex = new RegExp(`(${word})`, 'gi');
                processed = processed.replace(regex, '<span class="highlight">$1</span>');
            });
            return processed;
        }

        socket.on('connect', () => {
            status.innerText = "Connected to Server";
            status.style.color = "lime";
        });

        socket.on('disconnect', () => {
            status.innerText = "Disconnected";
            status.style.color = "red";
        });

        socket.on('caption_update', (data) => {
            let div = document.getElementById('msg-' + data.id);
            const isAtBottom = (window.innerHeight + window.scrollY) >= document.body.offsetHeight - 150;
            if (!div) {
                div = document.createElement('div');
                div.id = 'msg-' + data.id;
                div.className = 'caption-line';
                div.innerHTML = `<div class="speaker">${data.speaker || ''}</div><div class="text"></div>`;
                container.appendChild(div);
            }
            const textEl = div.querySelector('.text');
            if (textEl.innerText !== data.text) textEl.innerHTML = processText(data.text);
            if (data.speaker) div.querySelector('.speaker').innerText = data.speaker;
            if (isAtBottom) window.scrollTo(0, document.body.scrollHeight);
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index(): return render_template_string(HTML_TEMPLATE, keywords=KEYWORDS)

last_log_msg = ""
def log_status(msg):
    global last_log_msg
    if msg != last_log_msg:
        print(msg)
        last_log_msg = msg

# ==========================================
# RECURSIVE MESSAGE FINDER
# ==========================================
def find_first_message_node(control, current_depth=0, max_depth=6):
    if current_depth > max_depth: return None
    if not control: return None
    try:
        child = control.GetFirstChildControl()
        while child:
            name = child.Name
            # Criteria: Has text, AND is not the header
            if name and name.strip() != "" and name != "Live Captions" and name != "ライブ キャプション":
                if child.ControlTypeName in ['GroupControl', 'TextControl']: return control
            # Criteria: Empty Wrapper
            if child.ControlTypeName == 'GroupControl' and (not name or name.strip() == ""):
                found = find_first_message_node(child, current_depth + 1, max_depth)
                if found: return found
            child = child.GetNextSiblingControl()
    except: return None
    return None

# ==========================================
# SCRAPER LOGIC
# ==========================================
def capture_loop():
    print(f"--- Saving logs to: {log_filepath} ---")
    
    # Cache variable for the found UI element
    lc_group = None
    
    # Timing variable for log throttling
    last_save_time = time.time()
    
    with auto.UIAutomationInitializerInThread(debug=False):
        while True:
            try:
                # 1. SEARCH / VERIFY CACHE
                # If we don't have the group cached, or it is no longer valid (window closed), search for it.
                if lc_group is None or not lc_group.Exists(0, 0):
                    log_status("🔍 Scanning for Teams 'Live Captions' window...")
                    lc_group = None # Reset to be sure
                    
                    root = auto.GetRootControl()
                    for window in root.GetChildren():
                        if window.ControlTypeName != "WindowControl": continue
                        
                        # Only look in Teams processes
                        if "teams" in get_process_name(window.ProcessId):
                            # Try English name
                            temp_lc = window.Control(Name="Live Captions", searchDepth=SEARCH_DEPTH)
                            if not temp_lc.Exists(0,0): 
                                # Try Japanese name
                                temp_lc = window.Control(Name="ライブ キャプション", searchDepth=SEARCH_DEPTH)
                            
                            if temp_lc.Exists(0,0):
                                lc_group = temp_lc
                                log_status(f"✅ Found 'Live Captions' in window: {window.Name[:30]}...")
                                break
                    
                    if lc_group is None:
                        # Still not found, wait and retry
                        time.sleep(2)
                        continue

                # 2. RECURSIVE SEARCH (on the cached element)
                # We use the cached lc_group here
                start_node = find_first_message_node(lc_group)

                if not start_node:
                    log_status("⚠️ Connected, but no text found yet (Waiting for speech...)")
                    time.sleep(1)
                    continue

                # 3. CAPTURE LOOP
                has_new_updates = False
                log_status(f"🟢 Capturing...")
                line_item = start_node

                while line_item:
                    try:
                        if line_item.Name == "Close" or line_item.ControlTypeName == "ButtonControl": break
                        
                        runtime_id = "_".join(map(str, line_item.GetRuntimeId()))
                        content, speaker = "", ""

                        # Walker for texts
                        child_walker = line_item.GetFirstChildControl()
                        texts = []
                        while child_walker:
                            if child_walker.ControlTypeName == 'TextControl': texts.append(child_walker.Name)
                            child_walker = child_walker.GetNextSiblingControl()
                        
                        if len(texts) >= 2: speaker = texts[0]; content = texts[-1]
                        elif len(texts) == 1: content = texts[0]
                        else: content = line_item.Name

                        if content and content.strip():
                            # EMIT TO WEB
                            socketio.emit('caption_update', {'id': runtime_id, 'text': content, 'speaker': speaker})
                            
                            # UPDATE MEMORY
                            if runtime_id not in transcript_memory or transcript_memory[runtime_id]['text'] != content:
                                transcript_memory[runtime_id] = {
                                    'time': datetime.datetime.now().strftime("%H:%M:%S"),
                                    'speaker': speaker, 'text': content
                                }
                                has_new_updates = True
                    except: pass
                    line_item = line_item.GetNextSiblingControl()
                
                # 4. THROTTLED LOGGING
                # Only write to file if there were updates AND enough time has passed
                if has_new_updates and (time.time() - last_save_time > LOG_INTERVAL_SECONDS):
                    update_log_file()
                    last_save_time = time.time()
                
                time.sleep(0.1)

            except Exception as e:
                print(f"🔥 Error: {e}")
                # If an error occurs (e.g. window closed), reset the cache so we scan again
                lc_group = None 
                time.sleep(2)

if __name__ == '__main__':
    t = threading.Thread(target=capture_loop); t.daemon = True; t.start()
    print(f"Server starting at http://localhost:{PORT}")
    socketio.run(app, debug=False, host='0.0.0.0', port=PORT)