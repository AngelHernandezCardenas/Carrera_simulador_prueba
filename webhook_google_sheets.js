function doPost(e) {
  try {
    // Check if the request has a JSON payload
    if (!e || !e.postData || !e.postData.contents) {
      return ContentService.createTextOutput(JSON.stringify({status: "error", message: "No data received"}))
                           .setMimeType(ContentService.MimeType.JSON);
    }
    
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
    var data = JSON.parse(e.postData.contents);
    
    // Extract variables from the JSON payload
    var hora = data.hora || "";
    var juez = data.juez || "";
    var checkpoint = data.checkpoint || "";
    var equipo = data.equipo || "";
    var blanca = data.blanca || 0;
    var roja = data.roja || 0;
    var negra = data.negra || 0;
    
    // Append the row to the active sheet
    // Columns: Hora (A), Juez (B), Checkpoint (C), Equipo (D), Blanca (E), Roja (F), Negra (G)
    sheet.appendRow([hora, juez, checkpoint, equipo, blanca, roja, negra]);
    
    return ContentService.createTextOutput(JSON.stringify({status: "success"}))
                         .setMimeType(ContentService.MimeType.JSON);
                         
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({status: "error", message: error.toString()}))
                         .setMimeType(ContentService.MimeType.JSON);
  }
}
