Here is the fully updated SCANNER_STYLE_GUIDE.md. It now explicitly includes the Scan triggers in the footer and the Conflict Resolution Modal specifications, matching Scanner v28.

📄 Inventory Hub Scanner - Design Standard (v28+)
Core Philosophy: "Cyberpunk Dashboard." The interface must feel like a dedicated hardware terminal—stable, high-contrast, and information-dense, using specific ASCII borders and Emoji indicators.

1. Visual Layout (The "Dashboard")
The main screen must always clear and redraw in this exact order:

Double-Line Header: ======= (Width 60 chars).

Title Centered: 📡 INVENTORY DASHBOARD vXX.

Status Grid:

HUB / SPOOLMAN / FILABRIDGE status.

Use Green/Red Circles (🟢/🔴) for online/offline.

Undo Counter: UNDO STEPS: [X] Available.

Buffer Area:

Header: 📦 BUFFER: [ N ] Spools.

List Items: N. [COLOR_BLOCK] #{ID} {Display Name} (Truncated to fit).

Message Console:

Success: ✅ {Message}.

Error/Warning: ⚠️ {Error}.

Control Footer:

Must explicitly list available triggers and shortcuts in this order:

[Scan Spool] Add Item to Buffer

[Scan Loc] Move Buffer to Location

[Ctrl+Z] Undo Last Action

[Ctrl+L] Clear Buffer

[Ctrl+C] Quit

2. Visual Layout (The "Conflict Modal")
When a move conflict occurs (Occupancy or Physics), the screen must clear and render a dedicated warning modal:

Alert Header: 🛑 CONFLICT DETECTED 🛑 (Red).

Conflict Details:

Type: ⚠️ LOCATION OCCUPIED or ⚠️ PHYSICAL ERROR.

Description text from server.

Context Data:

Current Occupant: 🔵 CURRENTLY THERE: 🧵 {Name}.

Incoming Data: 🟢 INCOMING: 📦 {Count} New Item(s).

Action Menu:

[O] OVERWRITE (Evict old item to storage)

[C] CANCEL (Stop everything)

Interaction: This screen runs its own input loop and must capture O, C, or Ctrl+C.

3. Technical Constraints (Do Not Break)
Input Handling: NEVER use input() or blocking loops. Use msvcrt (Windows) and termios (Linux) to capture raw keypresses to allow for modal interactions.

Safe Keys:

Quit: Ctrl+C (ASCII \x03)

Clear: Ctrl+L (ASCII \x0c)

Undo: Ctrl+Z (ASCII \x1a)

Windows Encoding: The script MUST include this block at the top to prevent Emoji crashes on Windows:

Python

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    os.system('color')
4. Color Rendering Standard
Do not use generic text colors for filaments. Use this exact TrueColor ANSI function to render physical swatches:

Python

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