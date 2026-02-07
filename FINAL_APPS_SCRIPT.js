/**
 * ------------------------------------------------------------------
 * FINAL UPDATED APPS SCRIPT
 * ------------------------------------------------------------------
 * Copy ALL of this code and paste it into your Google Apps Script editor.
 * Then, you MUST click "Deploy" > "Manage deployments" > "Edit" > "New Version" > "Deploy".
 * ------------------------------------------------------------------
 */

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      throw new Error("Invalid POST request received.");
    }

    const postData = JSON.parse(e.postData.contents);
    const action = postData.action;
    let result;

    if (action === 'extract') {
      result = extractData(postData.photo1Base64);
    } else if (action === 'save') {
      result = saveData(postData.extractedData, postData.photo1Base64, postData.photo2Base64);
    } else {
      throw new Error("Invalid action specified: " + action);
    }
    
    return ContentService
      .createTextOutput(JSON.stringify({ success: true, data: result }))
      .setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ success: false, message: "Script Error: " + err.message }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function extractData(photo1Base64) {
  // NOTE: This URL works only if you have a deployed public backend.
  // Localhost (127.0.0.1) cannot be reached from Google Apps Script.
  const PYTHON_BACKEND_URL = "https://ocr-reader-botivate.onrender.com";
  
  const options = {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify({ base64Image: photo1Base64 }),
    muteHttpExceptions: true 
  };
  
  const response = UrlFetchApp.fetch(PYTHON_BACKEND_URL + "/ocr", options);
  if (response.getResponseCode() !== 200) {
    throw new Error("AI Server Error: " + response.getContentText());
  }
  return JSON.parse(response.getContentText());
}

function saveData(extractedData, photo1Base64, photo2Base64) {
  // --- CONFIGURATION ---
  const SHEET_ID = "1n5EnD8dMtFsbdDlIQcYt8F4QJ5rngTHMOx5hNvjgr5s";
  const FOLDER_ID = "1zggOUpg0SfMdi5LAXIfIWqZcBGMGHmMz";
  const SHEET_NAME = "Ai Card";
  // ---------------------

  // 1. Debugging Sheet Access
  let sheet;
  try {
    const ss = SpreadsheetApp.openById(SHEET_ID);
    sheet = ss.getSheetByName(SHEET_NAME);
    if (!sheet) throw new Error("Sheet with name '" + SHEET_NAME + "' not found.");
  } catch (e) {
    throw new Error("FAILED to access Spreadsheet. Check SHEET_ID or Sheet Name. Details: " + e.message);
  }

  // 2. Debugging Folder Access
  let folder;
  try {
    folder = DriveApp.getFolderById(FOLDER_ID);
  } catch (e) {
    throw new Error("FAILED to access Drive Folder. Check FOLDER_ID. Details: " + e.message);
  }

  const timestamp = new Date();

  // 3. Save Image 1
  let url1 = "";
  try {
    const blob1 = Utilities.newBlob(Utilities.base64Decode(photo1Base64), "image/png", "photo1_" + timestamp.getTime() + ".png");
    const file1 = folder.createFile(blob1);
    url1 = file1.getUrl();
  } catch (e) {
    throw new Error("Failed to save Image 1: " + e.message);
  }

  // 4. Save Image 2
  let url2 = "";
  if (photo2Base64 && photo2Base64.trim() !== "") {
    try {
      const blob2 = Utilities.newBlob(Utilities.base64Decode(photo2Base64), "image/png", "photo2_" + timestamp.getTime() + ".png");
      const file2 = folder.createFile(blob2);
      url2 = file2.getUrl();
    } catch (e) {
      // Non-fatal error for image 2
      url2 = "Error saving image 2: " + e.message;
    }
  }

  // 5. Hyperlink Logic
  let validationLink = extractedData.validation_source || "";
  const companyName = extractedData.company || "Source";
  
  if (extractedData.is_validated && extractedData.validation_source) {
    // Escape double quotes to be safe in formula
    const safeUrl = extractedData.validation_source.replace(/"/g, '""');
    const safeName = companyName.replace(/"/g, '""');
    validationLink = `=HYPERLINK("${safeUrl}", "${safeName} Link")`;
  }

  // 6. Append Row (Columns A-L)
  sheet.appendRow([
    timestamp,                          // A
    url1,                               // B
    url2,                               // C
    extractedData.company || "",        // D
    extractedData.name || "",           // E
    extractedData.phone || "",          // F
    extractedData.email || "",          // G
    extractedData.address || "",        // H
    extractedData.is_validated,         // I
    validationLink,                     // J
    extractedData.about_the_company || "", // K
    extractedData.location || ""          // L
  ]);
  
  return { message: "✅ Data saved successfully!" };
}
