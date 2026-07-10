function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return ContentService.createTextOutput(JSON.stringify({status: "error", message: "No data received"})).setMimeType(ContentService.MimeType.JSON);
    }
    
    var spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
    
    // INTENTAMOS ENCONTRAR LA PESTAÑA CORRECTA PARA GUARDAR LOS ESCANEOS
    // Cambia "Loading" por el nombre exacto de tu pestaña donde se guardan las pelotas
    var sheetNameForScans = "Loading"; 
    var sheet = spreadsheet.getSheetByName(sheetNameForScans);
    
    // Si no existe la pestaña "Loading", buscamos una que NO sea el Scoreboard
    if (!sheet) {
      var allSheets = spreadsheet.getSheets();
      for (var i = 0; i < allSheets.length; i++) {
        var tempName = allSheets[i].getName().toLowerCase();
        // Evitamos guardar en el Scoreboard accidentalmente
        if (!tempName.includes("scoreboard") && !tempName.includes("puntaje")) {
          sheet = allSheets[i];
          break;
        }
      }
    }
    
    // Si de plano no encontramos ninguna otra, usamos la primera por defecto
    if (!sheet) {
      sheet = spreadsheet.getSheets()[0];
    }
    
    var data = JSON.parse(e.postData.contents);
    
    var hora = data.hora || "";
    var juez = String(data.juez || "");
    var checkpoint = String(data.checkpoint || "");
    var equipo = String(data.equipo || "");
    var blanca = data.blanca || 0;
    var roja = data.roja || 0;
    var negra = data.negra || 0;
    
    var score = blanca * 1 + roja * 3 + negra * 5;
    
    // Si el juez es de Home-Base, actualizamos la tabla Loads (celdas B14:B28 y C14:C28)
    if (checkpoint === "4" || checkpoint === "Home-Base") {
      var loadsSheet = spreadsheet.getSheets().filter(function(s) { return s.getSheetId() == 572975250; })[0];
      if (loadsSheet) {
        var teamNum = parseInt(equipo.replace("Participante_", "")) || 0;
        if (teamNum >= 1 && teamNum <= 15) {
          var rowIndex = 13 + teamNum;
          var currentB = Number(loadsSheet.getRange(rowIndex, 2).getValue()) || 0;
          var currentC = Number(loadsSheet.getRange(rowIndex, 3).getValue()) || 0;
          
          var newB = currentB + score;
          var newC = Math.max(0, currentC - score);
          
          loadsSheet.getRange(rowIndex, 2).setValue(newB);
          loadsSheet.getRange(rowIndex, 3).setValue(newC);
        }
      }
      
      return ContentService.createTextOutput(JSON.stringify({status: "success", msg: "Home-Base load saved"})).setMimeType(ContentService.MimeType.JSON);
    }
    
    // Si es un juez NORMAL, guarda el escaneo como siempre
    sheet.appendRow([hora, juez, checkpoint, equipo, blanca, roja, negra, score]);
    
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
      var sheets = spreadsheet.getSheets();
      
      var data = null;
      var headerRowIndex = -1;
      var targetSheet = null;
      
      // Buscar en TODAS las pestañas cuál es la que tiene el Scoreboard (buscando "Rank" y "Team")
      for (var s = 0; s < sheets.length; s++) {
        var tempSheet = sheets[s];
        var tempData = tempSheet.getDataRange().getDisplayValues();
        
        for (var i = 0; i < tempData.length; i++) {
          var rowStr = tempData[i].join("").toLowerCase();
          if (rowStr.includes("rank") && rowStr.includes("team")) {
            headerRowIndex = i;
            data = tempData;
            targetSheet = tempSheet;
            break;
          }
        }
        if (headerRowIndex !== -1) {
          break; // Ya encontramos la hoja correcta
        }
      }
      
      if (headerRowIndex === -1) {
        return ContentService.createTextOutput(JSON.stringify({error: "No se encontraron los encabezados Rank y Team en ninguna pestaña"})).setMimeType(ContentService.MimeType.JSON);
      }
      
      var result = [];
      var headers = data[headerRowIndex];
      
      for (var i = headerRowIndex + 1; i < data.length; i++) {
        var row = data[i];
        var obj = {};
        for (var j = 0; j < headers.length; j++) {
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
