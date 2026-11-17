"""Retired 2026-11-16 (Group 68.3): the one-time move of product links out of spool comments.

Its job was done long ago: no prod spool held any comment text when it was retired. update.sh ran it at
every deploy, where a link typed into a spool's comment since would have become that spool's product link.

update.sh no longer calls it. This stub stays for the deploy that brings that change: that deploy still runs
prod's OLD update.sh to its end (git replaces the file with a new one, and bash keeps reading the one it
opened), and the old update.sh calls this file after the checkout. Delete it (Group 68) once a deploy has
run an update.sh without that line, and once the TrueNAS cron job is known to run the update.sh in the repo:
a copy kept anywhere else would still call this file.

It imports nothing and changes nothing.
"""

print("migrate_spool_links.py: retired (Group 68.3), nothing to do.")
