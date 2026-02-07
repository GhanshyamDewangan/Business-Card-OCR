# Google Apps Script Setup & Deployment Guide

Follow these steps EXACTLY to fix the "No item with the given ID" error and ensure your data is saved to Google Sheets.

## Prerequisites

1.  **Google Sheet**: A sheet named `Ai Card` (case-sensitive) with columns A-L.
2.  **Google Drive Folder**: A folder to save images.

---

## Step 1: Get Correct IDs

**Do not guess these IDs.** Copy them directly from the browser URL.

1.  **Sheet ID**:
    - Open your Google Sheet.
    - Look at the URL: `https://docs.google.com/spreadsheets/d/1n5EnD8dMtFsbdDlIQcYt8F4QJ5rngTHMOx5hNvjgr5s/edit...`
    - Copy the long string between `/d/` and `/edit`.
    - **Current ID in your code**: `1n5EnD8dMtFsbdDlIQcYt8F4QJ5rngTHMOx5hNvjgr5s` (Double check this matches YOUR URL).

2.  **Folder ID**:
    - Open your Google Drive and navigate to the folder where you want to save images.
    - Look at the URL: `https://drive.google.com/drive/folders/1zggOUpg0SfMdi5LAXIfIWqZcBGMGHmMz`
    - Copy the text after `folders/`.
    - **Current ID in your code**: `1zggOUpg0SfMdi5LAXIfIWqZcBGMGHmMz` (Double check this matches YOUR URL).

---

## Step 2: Update Apps Script Code

1.  Go to **Extensions > Apps Script** in your Google Sheet.
2.  Paste the code below (removing any old code).
3.  **CRITICAL**: Replace the IDs in the code with the ones you copied in Step 1.

```javascript
function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      throw new Error("Invalid POST request received.");
    }

    const postData = JSON.parse(e.postData.contents);
    const action = postData.action;
    let result;

    if (action === "save") {
      result = saveData(
        postData.extractedData,
        postData.photo1Base64,
        postData.photo2Base64,
      );
    } else {
      result = { message: "Ignored action: " + action };
    }

    return ContentService.createTextOutput(
      JSON.stringify({ success: true, data: result }),
    ).setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(
      JSON.stringify({
        success: false,
        message: "Script Error: " + err.message,
      }),
    ).setMimeType(ContentService.MimeType.JSON);
  }
}

function saveData(extractedData, photo1Base64, photo2Base64) {
  // *** UPDATE THESE IDs ***
  const SHEET_ID = "1n5EnD8dMtFsbdDlIQcYt8F4QJ5rngTHMOx5hNvjgr5s"; // <--- PASTE YOUR SHEET ID HERE
  const FOLDER_ID = "1zggOUpg0SfMdi5LAXIfIWqZcBGMGHmMz"; // <--- PASTE YOUR FOLDER ID HERE
  // ************************

  const sheet = SpreadsheetApp.openById(SHEET_ID).getSheetByName("Ai Card");
  if (!sheet) throw new Error("Sheet 'Ai Card' not found. Check casing!");

  const folder = DriveApp.getFolderById(FOLDER_ID);

  const timestamp = new Date();

  // Image 1
  const blob1 = Utilities.newBlob(
    Utilities.base64Decode(photo1Base64),
    "image/png",
    "photo1_" + timestamp.getTime() + ".png",
  );
  const file1 = folder.createFile(blob1);
  const url1 = file1.getUrl();

  // Image 2
  let url2 = "";
  if (photo2Base64) {
    const blob2 = Utilities.newBlob(
      Utilities.base64Decode(photo2Base64),
      "image/png",
      "photo2_" + timestamp.getTime() + ".png",
    );
    const file2 = folder.createFile(blob2);
    url2 = file2.getUrl();
  }

  // Formatting Validation Link
  let validationLink = extractedData.validation_source || "";
  if (extractedData.validation_source && extractedData.company) {
    validationLink =
      '=HYPERLINK("' +
      extractedData.validation_source +
      '", "' +
      extractedData.company +
      ' Link")';
  }

  sheet.appendRow([
    timestamp,
    url1,
    url2,
    extractedData.company || "",
    extractedData.name || "",
    extractedData.phone || "",
    extractedData.email || "",
    extractedData.address || "",
    extractedData.is_validated,
    validationLink,
    extractedData.about_the_company || "",
    extractedData.location || "",
  ]);

  return { message: "Data saved successfully!" };
}
```

4.  **SAVE** the script (`Ctrl + S`).

---

## Step 3: Deploy Properly (CRITICAL)

**This is where most errors happen.** If you don't do this, your changes (including new IDs) won't take effect.

1.  Click the blue **Deploy** button (top right).
2.  Select **New deployment**.
    - **Description**: "Updated IDs"
    - **Web App**:
      - **Execute as**: `Me` (your email).
      - **Who has access**: `Anyone`.
3.  Click **Deploy**.
4.  **Authorize Access**:
    - It will ask you to authorize. Click "Review permissions".
    - Select your account.
    - If you see "Google hasn't verified this app", click **Advanced** -> **Go to (Project Name) (unsafe)** -> **Allow**.
5.  **Copy the Web App URL**. It will end in `/exec`.

---

## Step 4: Update Your Environment

1.  Open `.env` file in your project folder.
2.  Update `APPS_SCRIPT_URL` with the **NEW** URL you just copied.
    ```
    APPS_SCRIPT_URL=https://script.google.com/macros/s/..../exec
    ```
3.  Save the `.env` file.
4.  Restart your Python server.

---

## Troubleshooting "No item with the given ID"

If you STILL get this error, it means the Google Account running the script (YOU) does not have permission to access the Sheet or Folder ID you pasted.

- Ensure you own the Sheet and Folder.
- Ensure the IDs are copied exactly (no spaces).
