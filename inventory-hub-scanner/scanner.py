import time, sys, requests, json, os, traceback

HUB_IP = "192.168.1.29"; HUB_URL = f"http://{HUB_IP}:8000/api"

if sys.platform == "win32": sys.stdout.reconfigure(encoding='utf-8'); os.system('color')

try:
    import msvcrt
    def get_key():
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            if ch == b'\x03': return 'CTRL_C'
            if ch == b'\x0c': return 'CTRL_L'
            if ch == b'\x1a': return 'CTRL_Z'
            if ch == b'\x12': return 'CTRL_R'
            if ch == b'\r': return '\n'
            try: return ch.decode('utf-8')
            except: return None
        return None
    def clear_screen(): os.system('cls')
except ImportError:
    import select, termios, tty
    def get_key():
        fd = sys.stdin.fileno(); old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd); r, _, _ = select.select([sys.stdin], [], [], 0.1)
            if r:
                ch = sys.stdin.read(1)
                if ch == '\x03': return 'CTRL_C'
                if ch == '\x0c': return 'CTRL_L'
                if ch == '\x1a': return 'CTRL_Z'
                if ch == '\x12': return 'CTRL_R'
                return ch
            return None
        finally: termios.tcsetattr(fd, termios.TCSADRAIN, old)
    def clear_screen(): print("\033[H\033[J", end="")

def render_color_blocks(color_list):
    if not color_list: return "   "
    blocks = ""
    for hex_str in color_list[:4]: 
        try:
            hex_str = hex_str.strip().lstrip('#')
            r, g, b = tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
            blocks += f"\033[48;2;{r};{g};{b}m  \033[49m"
        except: pass 
    return blocks

def api_call(endpoint, payload=None):
    try:
        url = f"{HUB_URL}/{endpoint}"
        resp = requests.post(url, json=payload, timeout=20) if payload else requests.get(url, timeout=5)
        resp.raise_for_status(); return resp.json()
    except Exception as e: return {"type": "error", "msg": f"Connection Error: {e}"}

def refresh_ui(buffer, last_msg, last_error):
    clear_screen(); status = api_call("status")
    if "type" in status: status = {}
    undo_count = status.get('undo_available', 0)
    icon = lambda x: "🟢" if x else "🔴"
    
    print("="*60)
    print(" 📡 INVENTORY DASHBOARD v32")
    print("="*60)
    print(f" HUB:        {icon('type' not in status)}")
    print(f" SPOOLMAN:   {icon(status.get('spoolman'))}")
    print(f" FILABRIDGE: {icon(status.get('filabridge'))}")
    print(f" UNDO STEPS: [{undo_count}] Available")
    print("-" * 60)
    print(f"\n 📦 BUFFER: [ {len(buffer)} ] Spools\n")
    
    if buffer:
        for idx, item in enumerate(buffer, 1):
            swatch = render_color_blocks(item.get('colors', []))
            print(f" {idx}. [{swatch}] {item['display'][:40]}")
    else: print("  (Buffer is empty. Scan spools to begin.)")
    print("")
    print("-" * 60)
    
    if last_msg:   print(f" ✅ {last_msg}")
    if last_error: print(f" ⚠️  {last_error}")
    
    print("\n COMMANDS:")
    print("  [Scan Spool]    Add Item to Buffer")
    print("  [Scan Loc]      Move Buffer to Location")
    print("  [Ctrl+Z]        Undo Last Action")
    print("  [Ctrl+R]        Remove Last Item")
    print("  [Ctrl+L]        Clear All")
    print("  [Ctrl+C]        Quit")
    print("="*60)

def main():
    buffer = []; input_buffer = ""; last_msg = ""; last_error = ""
    refresh_ui(buffer, last_msg, last_error)

    while True:
        key = get_key()
        if key:
            if key == 'CTRL_C': print("\nExiting..."); break
            elif key == 'CTRL_L': buffer = []; input_buffer = ""; last_msg = "Buffer Cleared."; last_error = ""; refresh_ui(buffer, last_msg, last_error)
            elif key == 'CTRL_R': 
                if buffer: buffer.pop(); last_msg = "Removed last item."
                else: last_error = "Buffer empty."
                refresh_ui(buffer, last_msg, last_error)
            elif key == 'CTRL_Z':
                last_msg = "Undoing..."; refresh_ui(buffer, last_msg, last_error)
                res = api_call("undo", {})
                last_msg = res.get('msg', ''); last_error = res.get('msg', 'Error') if not res.get('success') else ""
                refresh_ui(buffer, last_msg, last_error)

            elif key == '\r' or key == '\n':
                scan = input_buffer.strip(); input_buffer = ""
                if not scan: continue

                last_msg = f"Identifying: {scan}..."; refresh_ui(buffer, last_msg, last_error)
                res = api_call("identify_scan", {"text": scan})
                
                if res.get('type') == 'error': last_error = res['msg']; last_msg = ""
                elif res.get('type') == 'location':
                    target = res['id']
                    if not buffer:
                        contents = res.get('contents', [])
                        if contents:
                            for item in contents: buffer.append({"id": item['id'], "type": "spool", "display": item['display'], "colors": item['colors']})
                            last_msg = f"Loaded {len(contents)} items from {target}."; last_error = ""
                        else: last_error = f"{target} is empty."; last_msg = ""
                    else:
                        last_msg = f"Moving {len(buffer)} items to {target}..."; refresh_ui(buffer, last_msg, last_error)
                        ids = [x['id'] for x in buffer]
                        payload = {"spools": ids, "location": target, "force": False}
                        move_res = api_call("smart_move", payload)
                        
                        if move_res.get('status') == 'conflict':
                            c_type = move_res.get('type')
                            if c_type == 'physics': last_error = f"⛔ {move_res.get('msg')}"; last_msg = ""; move_res = {}
                            elif c_type in ['occupancy', 'quality']:
                                desc = move_res.get('desc', ''); msg = move_res.get('msg', '')
                                last_error = f"{msg}: {desc}"; last_msg = "FORCE? [Y] Yes / [N] No"; refresh_ui(buffer, last_msg, last_error)
                                proceed = False
                                while True:
                                    k = get_key()
                                    if k:
                                        if k.lower() == 'y': proceed = True; break
                                        if k.lower() == 'n' or k == 'CTRL_C': proceed = False; break
                                    time.sleep(0.01)
                                if proceed:
                                    last_msg = "Forcing Move..."; refresh_ui(buffer, last_msg, last_error)
                                    payload['force'] = True; move_res = api_call("smart_move", payload)
                                else: last_error = "Move Cancelled."; last_msg = ""; move_res = {}

                        if "log" in move_res:
                            msgs = []; errs = []
                            if "warning" in move_res: errs.append(move_res['warning'])
                            if "eviction" in move_res: msgs.append(move_res['eviction'])
                            ok = sum(1 for l in move_res['log'] if "Error" not in l and "Failed" not in l)
                            if ok > 0: msgs.append(f"Moved {ok} items.")
                            last_msg = " ".join(msgs); last_error = " ".join(errs) if errs else ""; buffer = [] 

                elif res.get('type') == 'spool':
                    sid = res['id']
                    if any(x['id'] == sid for x in buffer): last_error = f"Spool {sid} already in buffer."
                    else:
                        raw = res.get('display', f"#{sid}"); lbl = raw.split('\n')[1] if '\n' in raw else raw
                        buffer.append({"id": sid, "type": "spool", "display": f"#{sid} {lbl}", "colors": res.get('colors', [])})
                        last_msg = f"Added Spool {sid}"; last_error = ""
                else: last_error = "Unknown Barcode"; last_msg = ""
                refresh_ui(buffer, last_msg, last_error)

            else:
                if len(key) == 1 and key.isprintable(): input_buffer += key
        time.sleep(0.01)

if __name__ == "__main__":
    try: main()
    except: traceback.print_exc(); input()