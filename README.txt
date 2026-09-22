POI survey app
==============
1. Install Python 3.10+ from python.org (Windows: tick "Add Python to PATH").
2. Windows: double-click run.bat        Mac/Linux: ./run.sh
3. Your browser opens at http://localhost:5000
4. On a phone (same Wi-Fi as the computer): open the "On your phone" address printed in the window.

What's new in this version
- Height and Lens Model are no longer typed in. Enter Distance and pick a Viewing angle (6/7/8 deg);
  the app looks both up from the POI Camera Installation Table and shows them as read-only "AUTO" values.
- The POI Camera Installation Table itself is now a page in the generated Word report
  ("06: POI Camera Installation Table (Reference)"), colour-coded the same way as the source table.
- A distance outside the table (e.g. 333 m) is rejected with a clear message – the app never guesses
  a height or lens for it, on screen or in the report.
- "POI reference table (admin)" on the home screen lets you edit the table (heights, lens ranges,
  camera/vendor/install-type lists) as JSON. It's checked for overlaps, gaps and missing cells before
  saving, and reports use whatever table is saved at the time of generation.
  Optional: set the environment variable ADMIN_PIN before starting the app to require a PIN there.

Notes
- Drafts and photos are saved in the browser on the device you use (not on the server).
- Word preview appears only if LibreOffice is installed on the computer running the app.
- reference.default.json is the table as shipped (transcribed from your POI table image). Saving in the
  admin page writes reference.json alongside it; delete reference.json (or use "Reset to shipped
  default" in the app) to go back to the shipped table.
- Edit template.docx in Word to change fixed report text. Keep the {{TOKENS}} intact.
