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

function doGet(e) {
  var action = e.parameter.action;
  
  if (action === "getScoreboard") {
    try {
      var spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
      // Asegúrate de que exista una pestaña llamada "Scoreboard" en tu documento.
      // Si la pestaña se llama diferente (ej: "01 puntaje WonWheels"), cámbialo aquí.
      var sheet = spreadsheet.getSheetByName("Scoreboard") || spreadsheet.getActiveSheet(); 
      
      var data = sheet.getDataRange().getDisplayValues();
      var headers = data[0];
      var result = [];
      
      for (var i = 1; i < data.length; i++) {
        var row = data[i];
        var obj = {};
        for (var j = 0; j < headers.length; j++) {
          obj[headers[j]] = row[j];
        }
        // Solo agregamos si la fila tiene datos de un Team válido
        if (obj["Team"] || obj["Equipo"]) {
           result.push(obj);
        }
      }
      
      // Devolver los datos al Scoreboard en formato JSON
      return ContentService.createTextOutput(JSON.stringify(result))
                           .setMimeType(ContentService.MimeType.JSON);
    } catch (err) {
      return ContentService.createTextOutput(JSON.stringify({error: err.toString()}))
                           .setMimeType(ContentService.MimeType.JSON);
    }
  }
  
  return ContentService.createTextOutput(JSON.stringify({status: "ok", msg: "App is running"}))
                       .setMimeType(ContentService.MimeType.JSON);
}
