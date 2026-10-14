POI survey app
==============
1. Install Python 3.10+ from python.org (Windows: tick "Add Python to PATH").
2. Windows: double-click run.bat        Mac/Linux: ./run.sh
3. Your browser opens at http://localhost:5000
4. On a phone (same Wi-Fi as the computer): open the "On your phone" address printed in the window.

Access and data
- Login and user accounts are disabled. Anyone who can open the app can create surveys, view and
  delete the shared generated-report history, and use the report-generation API.
- Do not deploy this version to a public or untrusted network without protecting it with access
  controls at the hosting platform or behind a trusted private network.
- Drafts and photos are saved in the browser on the device being used. Generated-report history is
  shared by everyone and only kept for the most recent 24 hours.
- The database defaults to ~/.poi-survey/users.sqlite3. Set POI_DB_PATH to a writable persistent
  location when deploying (for example, /var/data/poi-survey.sqlite3 on a Render persistent disk).
  The previous POI_AUTH_DB variable is still supported for existing deployments.
- The built-in Flask server is for local/small-network use, not public deployment.

What's new in this version
- Height and Lens Model are no longer typed in. Enter Distance and pick a Viewing angle (6/7/8 deg);
  the app looks both up from the POI Camera Installation Table and shows them as read-only "AUTO" values.
- Select the grid button beside Height (m) in a survey to view the height reference image; close it
  to return to the survey.
- The POI Camera Installation Table itself is now a page in the generated Word report
  ("06: POI Camera Installation Table (Reference)"), colour-coded the same way as the source table.
- A distance outside the table (e.g. 333 m) is rejected with a clear message – the app never guesses
  a height or lens for it, on screen or in the report.
- Fractional distances use the lower whole-metre row in the shipped height schedule (for example,
  6.8 m uses the 6 m row, which includes a 2.2 m height).
- The POI reference table remains part of survey calculations and reports. To customize it, edit
  reference.json in the project directory; if it is absent, the shipped reference.default.json is used.
- Generated reports appear in the home-page history. Select individual reports or use "Select all",
  then choose
  "Delete selected" to remove them from the history; downloaded Word files are not deleted.

Notes
- Drafts and photos are saved in the browser on the device you use (not on the server); report
  history is stored in the server's local database.
- Word preview appears only if LibreOffice is installed on the computer running the app.
- reference.default.json is the table as shipped (transcribed from your POI table image). To use a
  custom table, add or edit reference.json alongside it; remove reference.json to restore the shipped
  default.
- Edit template.docx in Word to change fixed report text. Keep the {{TOKENS}} intact.
