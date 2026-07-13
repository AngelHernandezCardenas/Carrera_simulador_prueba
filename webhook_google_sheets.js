// Google Apps Script - Code.gs
// Webhook Definitivo para WonWheels
// Corregido: ahora enruta por "action" (update_home_base / update_loads)
// en lugar de por "checkpoint", ya que el backend envía checkpoint=99
// cuando el juez es Home-Base.

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return ContentService.createTextOutput(JSON.stringify({ status: "error", message: "No data received" })).setMimeType(ContentService.MimeType.JSON);
    }

    var data = JSON.parse(e.postData.contents);
    var ss = SpreadsheetApp.getActiveSpreadsheet();

    // 1. Calculamos el totalScore del escaneo
    var blanca = Number(data.blanca) || 0;
    var roja = Number(data.roja) || 0;
    var negra = Number(data.negra) || 0;
    var totalScore = (blanca * 1) + (roja * 3) + (negra * 5);

    // 2. Actualizamos "Load at home" y "Current load" en la hoja Loads
    var sheetLoads = ss.getSheetByName("Loads");
    if (sheetLoads) {
      var teamNumber = Number(data.team_number);
      if (teamNumber >= 1 && teamNumber <= 15) {
        var targetRow = 13 + teamNumber;

        var loadAtHomeCol = 2;  // Columna B
        var currentLoadCol = 3; // Columna C

        // === JUEZ HOME-BASE (checkpoint ID 4, "Rectoria-Descarga") ===
        if (data.action === "update_home_base") {
          var currentLoadAtHome = Number(sheetLoads.getRange(targetRow, loadAtHomeCol).getValue()) || 0;
          var currentCurrentLoad = Number(sheetLoads.getRange(targetRow, currentLoadCol).getValue()) || 0;
          
          var transfer = data.puntos_transferir !== undefined ? Number(data.puntos_transferir) : Math.min(currentCurrentLoad, totalScore);

          sheetLoads.getRange(targetRow, loadAtHomeCol).setValue(currentLoadAtHome + transfer);
          sheetLoads.getRange(targetRow, currentLoadCol).setValue(data.current_load !== undefined ? Number(data.current_load) : Math.max(0, currentCurrentLoad - transfer));
        }

        // === JUEZ NORMAL (checkpoints 1-10, excepto Home-Base) ===
        if (data.action === "update_loads") {
          var currentValue = Number(sheetLoads.getRange(targetRow, currentLoadCol).getValue()) || 0;

          // Sumamos el puntaje del escaneo a "Current load" sin tope forzoso
          sheetLoads.getRange(targetRow, currentLoadCol).setValue(data.current_load !== undefined ? Number(data.current_load) : (currentValue + totalScore));
        }

        // === CAMBIO DE COLOR DINÁMICO EN "CURRENT LOAD" ===
        var finalCurrentLoad = Number(sheetLoads.getRange(targetRow, currentLoadCol).getValue()) || 0;
        var currentLoadCell = sheetLoads.getRange(targetRow, currentLoadCol);
        if (finalCurrentLoad > 10) {
          currentLoadCell.setBackground("#ff0000"); // Rojo
        } else if (finalCurrentLoad === 10) {
          currentLoadCell.setBackground("#ffff00"); // Amarillo
        } else {
          currentLoadCell.setBackground(null); // Blanco (sin fondo)
        }
      }
    }
    
    // === TELEMETRÍA (Raspberry Pi) ===
    if (data.action === "update_telemetry") {
      var sheetEnergy = ss.getSheetByName("Energy");
      if (sheetEnergy) {
        var teamNumber = Number(data.team_number);
        if (teamNumber >= 1 && teamNumber <= 15) {
          var targetRow = 11 + teamNumber; // Row 12 is Team 1
          
          if (data.hora !== undefined) {
            sheetEnergy.getRange(targetRow, 3).setValue(data.hora); // Col C: Time
          }
          if (data.energia !== undefined && data.energia !== null) {
            sheetEnergy.getRange(targetRow, 4).setValue(Number(data.energia)); // Col D: Energy Wh
          }
          if (data.bateria !== undefined && data.bateria !== null) {
            sheetEnergy.getRange(targetRow, 6).setValue(Number(data.bateria) / 100.0); // Col F: % (as decimal for Sheets)
          }
        }
      }
      return ContentService.createTextOutput(JSON.stringify({ status: "ok", action: "update_telemetry" })).setMimeType(ContentService.MimeType.JSON);
    }

    // 3. Historial en "Loading" (AMBOS JUECES se guardan aquí)
    var sheetLoading = ss.getSheetByName("Loading");

    // Si no existe una pestaña llamada exactamente "Loading", buscamos una alterna
    // que no sea el Scoreboard ni la hoja de Puntaje, para no perder el historial.
    if (!sheetLoading) {
      var allSheets = ss.getSheets();
      for (var i = 0; i < allSheets.length; i++) {
        var tempName = allSheets[i].getName().toLowerCase();
        if (!tempName.includes("scoreboard") && !tempName.includes("puntaje") &&
          !tempName.includes("loads") && !tempName.includes("teams") &&
          !tempName.includes("jury") && !tempName.includes("stream") &&
          !tempName.includes("results") && !tempName.includes("challenges") &&
          tempName.indexOf("ch") !== 0) {
          sheetLoading = allSheets[i];
          break;
        }
      }
    }

    if (sheetLoading) {
      sheetLoading.appendRow([
        data.hora || "",
        data.juez || "",
        data.checkpoint || "",
        data.equipo || "",
        blanca,
        roja,
        negra,
        totalScore
      ]);
    }

    return ContentService.createTextOutput(JSON.stringify({ status: "ok", action: data.action })).setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ status: "error", message: err.toString() })).setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  var action = e && e.parameter ? e.parameter.action : null;

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
          break;
        }
      }

      if (headerRowIndex === -1) {
        return ContentService.createTextOutput(JSON.stringify({ error: "No se encontraron los encabezados Rank y Team en ninguna pestaña" })).setMimeType(ContentService.MimeType.JSON);
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
      return ContentService.createTextOutput(JSON.stringify({ error: err.toString() })).setMimeType(ContentService.MimeType.JSON);
    }
  }

  return ContentService.createTextOutput(JSON.stringify({ status: "ok", msg: "App is running" })).setMimeType(ContentService.MimeType.JSON);
}