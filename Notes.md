# ** update_from_csv.py **

Will add a new option in a multi-select "Choice" column that's in spoolman already? So adding a new filament type to the types choice list?

"No, it will not. And if you try, Spoolman will likely shout at us with a 400 Bad Request error."

This is a critical distinction between Data (The Spool) and Schema (The Rules).

1. The "Choice" Trap 🚫
If you have a field called Spool Type that allows ["Plastic", "Cardboard"], and you type Metal in your CSV:

The Script sends: "spool_type": "Metal"

Spoolman checks its list: "Is 'Metal' in my allowed list? No."

Result: Rejection. It will not save that change. It definitely won't auto-add "Metal" to the list for you.

To add a new option, you must explicitly tell Spoolman: "Hey, 'Metal' is now a legal option." You do this via the Settings UI or by re-running a setup script.

2. The "Filament Type" Confusion 🧶
You mentioned "Filament Type." In Spoolman, this usually refers to Material (PLA, PETG).

Material is a Filament Property, not a Spool Property.

Safety Rule #1: Our update_from_csv.py script ignores Filament data.

Why? If you change "PLA" to "PLA+" on one spool in your CSV, you are inadvertently changing it for every other spool that shares that filament definition. That is dangerous side-effect behavior.

📝 The Correct Workflow for New Options
If you need to add a new Spool Type (e.g., "Metal") or Material (e.g., "PVA"):

Step 1: Update the Rules (Schema)

Go to Spoolman Settings -> Extra Fields.

Edit Spool Type.

Add "Metal" to the list.

Save.

Step 2: Update the Data (CSV)

Now you can type "Metal" in your Excel file.

Step 3: Run the Updater

Now when the script sends "Metal", Spoolman says, "Ah, that is on the list now. Accepted!"

⚡ Summary
The Updater is a Data Pusher, not a Rule Maker. It plays by the rules that exist; it does not change them.