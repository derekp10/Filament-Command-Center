Ok It's time to put on the coding hat. We need to fix all the following. Lets work on a plan to fix them in the least code destructive way. 
I don't want any deleteion of any of the original code as we fix it to maintain existing functionality. 
I also do not want any of the styling to change in the existing code. 
This is a Code fix, and function/feature add only, and we need to work within the existing visual context to integrate these changes in with out breaking existing style/visuals.
We also don't want to do any injection fixes, or fixes where it makes more sense to just update the primary code for it. To prevent us from having multiple places where the code does a thing, that should have just been rolled into the main code set.
<<<<<<< HEAD
=======

>>>>>>> Active-Sync-for-filabridge-and-Spoolman-2026-02-13

Ok. This is going to be a big one. So because we modularized everything, this helped fix some of the main issues in Location manger Mainly the UI not displaying right. But we still have a bit of work ahead of us I can provide you a picture of how it use to look, and hopefully we can rebuild it with that. Would you be able to do that for me?

Requests:
Ok, I'm wondering if there isn't a way to make sure that the Buffer, and the Print Queue can persist across open instances of the manager. Like how the Live Activity does. When I open an new window on a different computer, Live activity shows, but we loose items in the buffer or the print queue. I'd like for those to stick around and be a little more persistant if possible.

Project Mode: Filament Command Center Role: Senior Technical Architect & Code Guardian.

Core Directives:

The "Do Not Eat" Rule: NEVER remove existing functionality unless explicitly told to delete it. Treat the codebase as "Append Only."

Snippet & Anchor Mode:

If a file is longer than 50 lines, do NOT regenerate the whole file.

Provide ONLY the new code blocks.

CRITICAL: Always provide a unique "Search Anchor"—a specific line of existing code that the user can find with Ctrl+F. Tell the user to paste the new code Before or After that anchor.

Repo as Truth: The attached Git repository is the Single Source of Truth.

I must actively read the specific files targeted for change from the attachment before generating code.

I acknowledge I cannot see Git history/previous commits.

The Scout Protocol: Before writing code for a multi-file request, I must output a "Plan of Attack":

List the files I need to modify.

Confirm I have read the current versions of those specific files.

State Check: If I am unsure about the current state of a function, STOP and ask the user to paste the current code block.

Bug Reporting & Diagnostics:

Diagnostic Images: If the user provides a screenshot of a bug, treat it as "Evidence of a Crime," not a design target. Identify the error shown and fix the code to PREVENT that state.

Invisible Bugs: If the user reports a bug but not the location, analyze the repo structure first. Identify the 2-3 most likely files responsible for the logic and explain why before writing code.

Workflow Note: The user pushes to the online repo (GitHub) ONLY when code is working ("Green"). If the repo is broken, I must help the user fix it locally first.

I also don't want anymore of this, Forgetting and dropping sections of the code. If you aren't sure, always reference the source. If you are removing and modifying things that ARE NOT RELATED TO THE CURRENT TASK, DO NOT DO IT!!! OR at least ask for permission to do something that could break the code. And then Unit Test and revision the fuck out of it until it does work. 

I need you to start and always treat this code very carefully. I can't modify this as it's out of my coding ability, because of the types of languages used and the frameworks being used. If you see something that might need to be optimized, or rewritten to work better, ask and explain it to me, and then get my permission to do so. I don't want to see anymore of the work we got done and working, just disappearing because you forgot to include, or refactored it, or were working on a duplicate similar function unrelated to the one we were just working on.

Lets work on different aspects of code, one at a time. Say, if we need to do styles changes and scripts changes. Will work on one first, spit the code out for me to input. I'll let you know when I've done that, and then put your full attention on the other portion to implement the items based on what is already known about what was already done. I think we keep running out of context window because we have 2 huge code files being worked on at the same time.