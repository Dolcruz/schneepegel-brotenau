# Schneepegelauswertung Brotenau

Dieses Repository enthält die lauffähige Auswertung für die fest installierte Kamera am Schneepegel Brotenau. Ein Bild wird eingelesen und als Schneehöhe, unsicher oder nicht auswertbar zurückgegeben.

Das Modell ist für diese Kamera, diesen Blickwinkel und diesen Pegel kalibriert. Es ist kein allgemeiner Schneedetektor für andere Standorte.

## Windows-App

Das Windows-Paket enthält die Oberfläche, Python und alle Modelle.
Es benötigt weder eine Installation von Python noch ein Konto oder eine Internetverbindung.

1. `Schneepegel_Brotenau_Setup.exe` öffnen und installieren.
2. **Schneepegel Brotenau** über das Desktopsymbol oder das Startmenü öffnen.
3. Bilder oder einen Bildordner hinzufügen. Die Auswertung beginnt automatisch.

Die Installation erfolgt im eigenen Windows-Benutzerkonto ohne Administratorrechte.
Unterstützt werden Windows 10 ab Version 1809 und Windows 11, jeweils x64.
Ein portables ZIP ist ebenfalls verfügbar: vollständig entpacken und die EXE
zusammen mit ihrem Ordner `_internal` aufbewahren.

Die große Originalansicht und die Bildliste stehen im Mittelpunkt. **Prüfen**
filtert unsichere, unbrauchbare und fehlerhafte Aufnahmen; die Suche findet Bilder
nach Dateiname. Unter **Schneehöhen** öffnet ein Klick auf einen Messpunkt das
zugehörige Original. Der Bildausschnitt bleibt beim Eintreffen von Ergebnissen
erhalten. Einzelne Bilder lassen sich erneut auswerten oder aus der Liste entfernen.
**Für Excel exportieren** speichert alle Ergebnisse. Fehlende Messwerte bleiben
leer; eine gemessene Null wird als `0` exportiert.

Bildliste und Ergebnisse werden unter
`%LOCALAPPDATA%\Brotenau\Schneepegel Brotenau\ergebnisse.sqlite3` gespeichert.
Die App referenziert die Originaldateien; sie kopiert oder verändert sie nicht.
Die Grafik verwendet die Importreihenfolge. Eingebrannte Zeitstempel bleiben im
Original sichtbar und werden nicht automatisch ausgelesen.

### Windows-Paket selbst bauen

Verwenden Sie eine normale 64-Bit-Installation von CPython 3.12 auf Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.12.0 torchvision==0.27.0
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
.\.venv\Scripts\python.exe build_windows.py
```

Das Ergebnis liegt unter `dist/Schneepegel Brotenau`. Der Build lädt einmalig die
ResNet-18-Gewichte, prüft ihren Hash und bündelt sie für den Offlinebetrieb.
Es gibt keinen separaten Server und keine GPU-Voraussetzung.
Der Build isoliert die native DLL-Suche von anderen auf dem Rechner installierten
Werkzeugen. Für den Installer anschließend mit Inno Setup 7 kompilieren:

```powershell
ISCC.exe installer.iss
```

Die Setup-Datei liegt unter `dist/installer`. Sie installiert unter
`%LOCALAPPDATA%\Programs\Schneepegel Brotenau`, erstellt Desktop- und
Startmenüverknüpfungen und registriert die Deinstallation. Gespeicherte Ergebnisse
werden bei einer Deinstallation beibehalten. Laufende Anwendungen werden vom
Installer nicht automatisch beendet oder neu gestartet. Komprimierung: ZIP,
Stufe 7, ein Komprimierungsthread. Dies beeinflusst keine Bildanalyse.

Für Paketdownloads gelten die pip-Standardwerte: 15 Sekunden Netzwerk-Wartezeit
und bis zu 5 Verbindungswiederholungen. Der Modellgewichte-Download verwendet den
Bibliotheksstandard ohne eigene Frist und ohne eigene Wiederholungsschleife.

### Ausführungsverhalten

Die App verarbeitet ein Bild gleichzeitig, ohne Analyse-Zeitlimit oder automatische
Wiederholungen. **Anhalten** und das Schließen während der Analyse wirken nach dem
laufenden Bild; dessen Ergebnis wird noch gespeichert. PyTorch und numerische
Bibliotheken nutzen 2 CPU-Threads, OpenCV 1, PyTorch Interop 1 und die drei
Höhenregressoren je 1 Worker. Es gibt keine feste Obergrenze für die Bildanzahl;
große Listen benötigen entsprechend mehr Arbeitsspeicher und Laufzeit. SQLite
wartet bei einer gesperrten Ergebnisdatenbank standardmäßig bis zu 5 Sekunden.
Die vorhandene Modellausgabe ist auf 0 bis 80 cm in 1-cm-Schritten ausgelegt;
die Schrittweite ist keine Messgenauigkeitsgarantie.

## Kommandozeile

Voraussetzung ist eine aktuelle Python-Version. Getestet wurde die Auswertung mit Python 3.13.

```powershell
git clone https://github.com/Dolcruz/schneepegel-brotenau.git
cd schneepegel-brotenau

py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Ein Bild auswerten:

```powershell
.\.venv\Scripts\python.exe -m height_model.predict_pipeline C:\Pfad\zum\bild.jpg
```

Mehrere Bilder können in einem Aufruf übergeben werden:

```powershell
.\.venv\Scripts\python.exe -m height_model.predict_pipeline C:\Bilder\bild1.jpg C:\Bilder\bild2.jpg
```

Beim ersten Start lädt `torchvision` einmalig die vortrainierten ResNet-18-Gewichte herunter. Danach kann die Auswertung lokal laufen.

## Erwartete Bilder

- Auflösung: 1920 x 1080 Pixel
- gleiche Kamera- und Pegelinstallation wie in Brotenau
- JPG oder PNG
- der Pegel sollte sich ungefähr im bekannten Bildbereich befinden

Andere Auflösungen oder deutlich veränderte Kamerapositionen werden nicht automatisch umgerechnet.

## Ausgabe

Pro Bild wird eine JSON-Zeile ausgegeben. Entscheidend sind `status`, `snow_height_cm` und `reason`.

Gemessene Schneehöhe:

```json
{"status": "measured", "snow_height_cm": 12.0, "reason": "positive_peg_model"}
```

Unsicheres Bild:

```json
{"status": "uncertain", "snow_height_cm": null, "reason": "geometric_models_disagree"}
```

Nicht auswertbares Bild:

```json
{"status": "unusable", "snow_height_cm": null, "reason": "quality_filter"}
```

Bei `uncertain` und `unusable` wird bewusst keine Schneehöhe erzwungen.

## So funktioniert die Auswertung

```text
Bild -> Bildqualität -> Schneekontext -> Pegel ausrichten -> Höhe schätzen -> Ergebnis prüfen
```

1. **Bildqualität prüfen.** Sind Pegel und Umgebung ausreichend sichtbar?
2. **Schneefreie Bilder erkennen.** Bei eindeutig schneefreier Umgebung werden 0 cm ausgegeben.
3. **Pegel ausrichten.** Drei Pegelbereiche werden an der Kalibrierung ausgerichtet und gleichen kleine Kamerabewegungen aus.
4. **Schneehöhe schätzen.** Schneegrenze und Bildmerkmale werden entlang der kalibrierten Pegelachse ausgewertet.
5. **Ergebnis freigeben.** Eine Zahl erscheint nur, wenn Geometrie, Pegelerkennung und Modellschätzungen ausreichend zusammenpassen.

Technisch kombiniert die Pipeline:

- ResNet-18-Bildmerkmale zur Erkennung unbrauchbarer Aufnahmen
- einen separaten Kontextklassifikator für eindeutig schneefreie Situationen
- Pegelanker zur Bildausrichtung
- ein Sichtbarkeitsprofil entlang der kalibrierten Pegelachse
- Extra-Trees-Regressoren für zusätzliche Pegel- und Umfeldmerkmale
- einen Sicherheitsrouter, der widersprüchliche Ergebnisse zurückhält

## Datengrundlage

- 666 manuell geprüfte Stationsbilder aus 74 TLC-Bildserien
- 571 Bilder mit einer eingetragenen Schneehöhe zwischen 0 und 25 cm
- 95 als nicht auswertbar markierte Bilder
- manuell gesetzte Messmarken für den Zentimeterbezug
- 710 synthetische Varianten von 10 bis 80 cm, zehn Bilder je Zentimeterstufe

Aufeinanderfolgende Bilder derselben TLC-Serie wurden bei der Prüfung nicht zwischen Training und Test aufgeteilt. Auch synthetische Varianten derselben Ausgangsaufnahme blieben zusammen. So konnten nahezu identische Bilder nicht gleichzeitig im Training und im Test landen.

Die ursprünglichen Stationsbilder und Trainingsdaten sind nicht Bestandteil dieses Repositorys. Für die Laufzeit liegen nur die trainierten Modelle, die Pegelkalibrierung und ein kompaktes Referenzpaket bei.

## Bisheriger Stand

In der gruppengetrennten Prüfung mit 710 synthetischen Bildern wurden 508 Bilder automatisch gemessen. Das entspricht einer Abdeckung von 71,5 Prozent. Von den freigegebenen Messungen lagen 98,4 Prozent innerhalb von +/- 2 cm; der mittlere absolute Fehler lag bei 0,23 cm.

Von den 95 manuell als nicht auswertbar markierten Stationsbildern wurden 92 automatisch abgelehnt.

## Bekannte Grenzen

- Reale Trainingsbilder über 25 cm fehlen bisher. Größere Höhen wurden hauptsächlich mit synthetischen Bildern geprüft.
- Tropfen, Schnee auf der Linse, Nebel und lokale Schmelzstellen können Pegel und Umgebung widersprüchlich erscheinen lassen.
- Eine deutliche Änderung der Kamera oder des Pegels erfordert eine neue Kalibrierung.
- Eine vollständig neue, zeitlich spätere Bildserie wurde noch nicht als unabhängiger Zukunftstest ausgewertet.

## Repository-Struktur

```text
height_model/
  predict_pipeline.py        Kommandozeilen-Aufruf
  features.py                Kontext- und Pegelmerkmale
  geometric_meter.py         Pegelausrichtung und geometrische Messung
  artifacts/                 trainierte Höhenmodelle
  resources/                 Kalibrierung und Referenzpaket
quality_model/
  artifacts/                 Modell für auswertbar / nicht auswertbar
docs/
  Schneepegel_Brotenau_Dokumentation.pdf
```

Eine kompakte PDF-Fassung liegt unter [`docs/Schneepegel_Brotenau_Dokumentation.pdf`](docs/Schneepegel_Brotenau_Dokumentation.pdf).
