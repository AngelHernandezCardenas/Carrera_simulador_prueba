function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return ContentService.createTextOutput(JSON.stringify({status: "error", message: "No data received"})).setMimeType(ContentService.MimeType.JSON);
    }
    
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
    var data = JSON.parse(e.postData.contents);
    
    var hora = data.hora || "";
    var juez = data.juez || "";
    var checkpoint = data.checkpoint || "";
    var equipo = data.equipo || "";
    var blanca = data.blanca || 0;
    var roja = data.roja || 0;
    var negra = data.negra || 0;
    
    sheet.appendRow([hora, juez, checkpoint, equipo, blanca, roja, negra]);
    
    return ContentService.createTextOutput(JSON.stringify({status: "success"})).setMimeType(ContentService.MimeType.JSON);
                         
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({status: "error", message: error.toString()})).setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  var action = e.parameter.action;
  
  if (action === "getScoreboard") {
    try {
      var spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
      var sheet = spreadsheet.getSheetByName("Scoreboard") || spreadsheet.getActiveSheet(); 
      
      var data = sheet.getDataRange().getDisplayValues();
      var result = [];
      
      // Buscar en qué fila están los encabezados (donde dice "Rank" y "Team")
      var headerRowIndex = -1;
      for (var i = 0; i < data.length; i++) {
        var rowStr = data[i].join("").toLowerCase();
        if (rowStr.includes("rank") && rowStr.includes("team")) {
          headerRowIndex = i;
          break;
        }
      }
      
      if (headerRowIndex === -1) {
        return ContentService.createTextOutput(JSON.stringify({error: "No se encontraron los encabezados Rank y Team"})).setMimeType(ContentService.MimeType.JSON);
      }
      
      var headers = data[headerRowIndex];
      
      for (var i = headerRowIndex + 1; i < data.length; i++) {
        var row = data[i];
        var obj = {};
        for (var j = 0; j < headers.length; j++) {
          // Remover espacios extra de los encabezados por si acaso
          var h = headers[j].trim();
          if (h) {
            obj[h] = row[j];
          }
        }
        if (obj["Team"] || obj["Equipo"]) {
           result.push(obj);
        }
      }
      
      return ContentService.createTextOutput(JSON.stringify(result)).setMimeType(ContentService.MimeType.JSON);
    } catch (err) {
      return ContentService.createTextOutput(JSON.stringify({error: err.toString()})).setMimeType(ContentService.MimeType.JSON);
    }
  }
  
  return ContentService.createTextOutput(JSON.stringify({status: "ok", msg: "App is running"})).setMimeType(ContentService.MimeType.JSON);
}
