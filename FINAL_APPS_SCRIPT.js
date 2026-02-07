/**
 * ------------------------------------------------------------------
 * FINAL UPDATED APPS SCRIPT (FULL VERSION)
 * ------------------------------------------------------------------
 * This script handles:
 * 1. GET requests (doGet) - Returns all data for the Leads Dashboard.
 * 2. POST requests (doPost) - Handles 'extract', 'save', and 'read' actions.
 * ------------------------------------------------------------------
 */

/**
 * Handle GET requests to fetch whole sheet data for the Dashboard.
 */
function doGet(e) {
  try {
    const sheetData = getSheetData();
    return ContentService
      .createTextOutput(JSON.stringify({ success: true, data: sheetData }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ success: false, message: "Script Error: " + err.message }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

/**
 * Handle POST requests for complex actions.
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
    } else if (action === 'read') {
      result = getSheetData();
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
  const SHEET_ID = "1c3v7DcBqfMK8yzPyMs3StwNj7bg7yc5gSnEsHnmuBlg";
  const FOLDER_ID = "1zggOUpg0SfMdi5LAXIfIWqZcBGMGHmMz";
  const SHEET_NAME = "Ai Card";
  // ---------------------

  let sheet;
  try {
    const ss = SpreadsheetApp.openById(SHEET_ID);
    sheet = ss.getSheetByName(SHEET_NAME);
    if (!sheet) throw new Error("Sheet with name '" + SHEET_NAME + "' not found.");
  } catch (e) {
    throw new Error("FAILED to access Spreadsheet. Check SHEET_ID or Sheet Name. Details: " + e.message);
  }

  let folder;
  try {
    folder = DriveApp.getFolderById(FOLDER_ID);
  } catch (e) {
    throw new Error("FAILED to access Drive Folder. Check FOLDER_ID. Details: " + e.message);
  }

  const timestamp = new Date();

  // Save Image 1
  let url1 = "";
  try {
    const blob1 = Utilities.newBlob(Utilities.base64Decode(photo1Base64), "image/png", "photo1_" + timestamp.getTime() + ".png");
    const file1 = folder.createFile(blob1);
    url1 = file1.getUrl();
  } catch (e) {
    throw new Error("Failed to save Image 1: " + e.message);
  }

  // Save Image 2
  let url2 = "";
  if (photo2Base64 && photo2Base64.trim() !== "") {
    try {
      const blob2 = Utilities.newBlob(Utilities.base64Decode(photo2Base64), "image/png", "photo2_" + timestamp.getTime() + ".png");
      const file2 = folder.createFile(blob2);
      url2 = file2.getUrl();
    } catch (e) {
      url2 = "Error saving image 2: " + e.message;
    }
  }

  // Hyperlink Logic
  let validationLink = extractedData.validation_source || "";
  const companyName = extractedData.company || "Source";

  if (extractedData.is_validated && extractedData.validation_source) {
    const safeUrl = extractedData.validation_source.replace(/"/g, '""');
    const safeName = companyName.replace(/"/g, '""');
    validationLink = `=HYPERLINK("${safeUrl}", "${safeName} Link")`;
  }

  // Format Key People (Founder/CEO + Contact)
  let keyPeopleString = "";
  if (extractedData.key_people && Array.isArray(extractedData.key_people)) {
    keyPeopleString = extractedData.key_people.map(p => {
      let details = p.name + " (" + p.role + ")";
      if (p.contact && p.contact !== "Not Found") {
        details += " - " + p.contact;
      }
      return details;
    }).join("\n");
  } else {
    let parts = [];
    if (extractedData.founder) parts.push("Founder: " + extractedData.founder);
    if (extractedData.ceo) parts.push("CEO: " + extractedData.ceo);
    if (extractedData.owner) parts.push("Owner: " + extractedData.owner);
    keyPeopleString = parts.join("\n");
  }

  // Append Row (Columns A-V)
  sheet.appendRow([
    timestamp,                          // A
    url1,                               // B
    url2,                               // C
    extractedData.company || "",        // D
    extractedData.industry || "",       // E 
    extractedData.name || "",           // F
    extractedData.title || "",          // G 
    extractedData.phone || "",          // H
    extractedData.email || "",          // I
    extractedData.website || "",        // J 
    extractedData.social_media || "",   // K 
    extractedData.address || "",        // L
    extractedData.services || "",       // M 
    extractedData.company_size || "",   // N 
    extractedData.established_year || extractedData.founded_year || "", // O 
    extractedData.registration_status || "", // P 
    extractedData.trust_score || "",    // Q
    keyPeopleString,                    // R 
    extractedData.is_validated,         // S
    validationLink,                     // T
    extractedData.about_the_company || "", // U
    extractedData.location || ""          // V
  ]);

  return { message: "✅ Data saved successfully!" };
}

/**
 * Helper function to fetch all data from the sheet for Dashboard viewing.
 */
function getSheetData() {
  const SHEET_ID = "1c3v7DcBqfMK8yzPyMs3StwNj7bg7yc5gSnEsHnmuBlg";
  const SHEET_NAME = "Ai Card";
  
  const ss = SpreadsheetApp.openById(SHEET_ID);
  const sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) throw new Error("Sheet not found: " + SHEET_NAME);
  
  const range = sheet.getDataRange();
  const values = range.getValues();
  const formulas = range.getFormulas();
  
  if (values.length < 2) return [];
  
  const headers = values[0];
  const data = [];
  
  for (let i = 1; i < values.length; i++) {
    const row = values[i];
    const rowFormulas = formulas[i];
    const obj = {};
    headers.forEach((header, index) => {
      // Use formula if it exists (for hyperlinks), otherwise use value
      obj[header] = rowFormulas[index] || row[index];
    });
    data.push(obj);
  }
  
  return data;
}
