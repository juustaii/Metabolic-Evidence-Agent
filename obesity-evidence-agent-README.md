# Obesity Evidence Agent

A single-file, browser-based obesity evidence assistant.

## What it does
- Lets a clinician ask a question
- Searches only the on-file repository
- Ranks guidelines, journal articles, and trials
- Shows citations and a strict `not found in the repository` fallback
- Lets you add documents, import TXT/MD/JSON/CSV, export data, and manage crawler queue items
- Persists settings and documents in localStorage

## Main file
- `/obesity-evidence-agent.html`

## How to use
1. Open the HTML file in a browser.
2. Add your obesity resources to the repository.
3. Tune relevance settings and source filters.
4. Ask questions in the search box.
5. Export JSON if you want to hand the data to a backend developer.

## Notes
- This is a working frontend prototype.
- It is ready to upload to a website or hand off as a final interactive demo.
- For a live web crawler and multi-user backend, connect the UI to your server/API later.
