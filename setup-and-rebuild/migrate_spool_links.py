import requests
import re
import json

import os
import sys

# Add inventory-hub to path to import config_loader
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'inventory-hub')))
import config_loader

SPOOLMAN_IP, _ = config_loader.get_api_urls()
print(f"🔗 Target Spoolman IP: {SPOOLMAN_IP}")

def clean_comment(comment_text):
    if not comment_text:
        return "", None

    # Regex to find standard HTTP/HTTPS URLs
    url_pattern = r'(https?://[^\s]+)'
    
    urls_found = re.findall(url_pattern, comment_text)
    
    if not urls_found:
        return comment_text, None

    # We just grab the first one we find since we only have one product_url field
    target_url = urls_found[0]
    
    # Clean the URL out of the comment entirely
    cleaned_comment = re.sub(url_pattern, '', comment_text)
    # Strip any dangling whitespace or newlines left behind by the removal
    cleaned_comment = cleaned_comment.strip()

    return cleaned_comment, target_url

def migrate_spool_links():
    try:
        print("🔍 Searching for Spools...")
        resp = requests.get(f"{SPOOLMAN_IP}/api/v1/spool")
        if not resp.ok:
            print(f"❌ Failed to reach Spoolman: {resp.status_code}")
            return
            
        spools = resp.json()
        print(f"📦 Found {len(spools)} Total Spools.")
        
        migrated_count = 0
        
        for spool in spools:
            sid = spool.get('id')
            comment = spool.get('comment', '')
            extra = spool.get('extra', {})
            
            # If there's no comment at all, move on.
            if not comment:
                continue
                
            new_comment, discovered_url = clean_comment(comment)
            
            if discovered_url:
                print(f"--- Spool #{sid} ---")
                print(f"   🔗 Found Link: {discovered_url}")
                print(f"   🧹 Old Comment: '{comment}'")
                print(f"   ✨ New Comment: '{new_comment}'")
                
                # Setup the patch payload
                # [ALEX FIX] Spoolman strictly requires text strings in the 'extra' dict to be valid JSON strings (wrapped in quotes)
                extra['product_url'] = f'"{discovered_url}"'
                
                payload = {
                    "comment": new_comment,
                    "extra": extra
                }
                
                patch_resp = requests.patch(f"{SPOOLMAN_IP}/api/v1/spool/{sid}", json=payload)
                if patch_resp.ok:
                    print("   ✅ Migrated Successfully.")
                    migrated_count += 1
                else:
                    print(f"   ❌ Migration Failed: {patch_resp.status_code} - {patch_resp.text}")

        print(f"\n🎉 Migration Complete! Successfully migrated {migrated_count} spools.")

    except Exception as e:
        print(f"❌ Connection Error: {e}")

if __name__ == "__main__":
    migrate_spool_links()
