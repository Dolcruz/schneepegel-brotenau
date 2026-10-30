# Schneepegel Brotenau

Schneehöhen aus den Bildern der Messstation Brotenau auswerten. Die Windows-App zeigt zu jedem Foto das Ergebnis und das Originalbild, fasst die Messwerte in einer Grafik zusammen und exportiert sie für Excel.

**[Für Windows herunterladen](https://github.com/Dolcruz/schneepegel-brotenau/releases/download/v1.0.0/Schneepegel_Brotenau_Setup.exe)** · [Alle Downloads](https://github.com/Dolcruz/schneepegel-brotenau/releases/tag/v1.0.0)

## Installation

Benötigt werden Windows 10 ab Version 1809 oder Windows 11, jeweils in der 64-Bit-Version für x64.

1. `Schneepegel_Brotenau_Setup.exe` herunterladen und öffnen.
2. Die Installation abschließen und **Schneepegel Brotenau** über das Startmenü oder das Desktopsymbol starten.
3. Mit **Bilder hinzufügen** einzelne Fotos oder mit **Ordner auswählen** einen ganzen Bildordner öffnen. Die Auswertung beginnt automatisch.

Python und die Modelle sind bereits enthalten. Die App arbeitet nach dem Download ohne Internetverbindung. Für die Installation sind keine Administratorrechte nötig.

Wer die App ohne Installation nutzen möchte, kann das portable ZIP herunterladen. Den gesamten Ordner entpacken und `Schneepegel Brotenau.exe` öffnen. Die EXE und der Ordner `_internal` müssen zusammenbleiben.

Installer und Anwendung sind nicht digital signiert.

## Bilder auswerten

Die Bildliste steht links, das ausgewählte Originalbild mit seinem Ergebnis rechts. Über die Suche lassen sich Bilder nach ihrem Dateinamen finden.

- **Gemessen** zeigt die Bilder mit einer ermittelten Schneehöhe.
- **Prüfen** sammelt unsichere, nicht auswertbare und fehlerhafte Aufnahmen. Bei diesen Bildern bleibt der Höhenwert offen.
- **Offen** zeigt Bilder, die noch nicht ausgewertet wurden.

Mit dem Mausrad lässt sich das Original vergrößern, durch Ziehen der Bildausschnitt verschieben. **Einpassen** zeigt wieder das ganze Foto. Im Reiter **Schneehöhen** führt ein Klick auf einen Messpunkt zum zugehörigen Bild. Die Grafik zeigt die Reihenfolge der importierten Bilder, keine Zeitachse.

**Anhalten** beendet die Verarbeitung nach dem laufenden Bild. Mit **Auswertung fortsetzen** geht es später weiter. Auch beim Schließen wird das laufende Bild noch fertig ausgewertet und gespeichert. Einzelne Aufnahmen können mit **Erneut auswerten** noch einmal geprüft werden.

**Für Excel exportieren** speichert die gesamte Bildliste als CSV-Tabelle. Fehlende Höhenwerte bleiben leer; eine gemessene Schneehöhe von null steht als `0` in der Tabelle.

### Gespeicherte Bilder und Ergebnisse

Die App merkt sich die Bildliste und die Ergebnisse automatisch. Bereits hinzugefügte Bilder werden beim nächsten Import übersprungen.

Die Originalfotos werden weder kopiert noch verändert. Sie sollten an ihrem Speicherort bleiben, damit die Vorschau sie weiterhin öffnen kann. Über **Mehr** lassen sich einzelne Einträge entfernen oder die Bildliste leeren. Die Originaldateien bleiben dabei erhalten.

Die Ergebnisdatenbank liegt unter `%LOCALAPPDATA%\Brotenau\Schneepegel Brotenau\ergebnisse.sqlite3` und bleibt auch nach einer Deinstallation erhalten.

## Welche Bilder passen?

Die Auswertung ist auf die fest installierte Kamera und den Schneepegel in Brotenau abgestimmt:

- JPG oder PNG mit 1920 × 1080 Pixeln
- gleicher Blickwinkel und gleiche Pegelposition wie bei den Stationsaufnahmen
- sichtbarer Pegel und ausreichend erkennbare Umgebung

Andere Auflösungen werden nicht automatisch angepasst. Bei einer deutlichen Veränderung der Kamera- oder Pegelposition muss die Kalibrierung erneuert werden. Eingebrannte Zeitstempel können im Originalbild abgelesen werden; die App übernimmt sie nicht automatisch.

## Wie die Auswertung funktioniert

Zunächst prüft das Programm die Bildqualität und erkennt eindeutig schneefreie Aufnahmen. Bei Bildern mit Schnee richtet es den Pegel an den Referenzaufnahmen aus und schätzt die Höhe anhand der Schneegrenze und der sichtbaren Pegelabschnitte. Widersprechen sich die Schätzungen, erscheint kein Höhenwert; das Bild wird zur Prüfung markiert.

Dafür werden ResNet-18-Bildmerkmale, ein Klassifikator für schneefreie Situationen, die Pegelgeometrie und mehrere Extra-Trees-Regressoren kombiniert. Modelle, Kalibrierung und Referenzdaten sind im Repository enthalten.

[Dokumentation zur Modellauswertung als PDF](docs/Schneepegel_Brotenau_Dokumentation.pdf)

### Daten und bisherige Prüfung

Die Datengrundlage umfasst 666 manuell geprüfte Stationsbilder aus 74 TLC-Bildserien. Für 571 Bilder wurden Schneehöhen zwischen 0 und 25 cm eingetragen; 95 Bilder wurden als nicht auswertbar markiert. Hinzu kommen manuell gesetzte Messmarken und 710 synthetische Bilder mit Schneehöhen von 10 bis 80 cm.

Für Training und Test wurden vollständige Bildserien getrennt. Synthetische Varianten derselben Ausgangsaufnahme blieben ebenfalls zusammen, damit nahezu identische Bilder nicht auf beiden Seiten der Prüfung vorkommen.

Bei der Prüfung mit 710 synthetischen Bildern wurden 508 automatisch gemessen, also 71,5 Prozent. Von diesen Messungen lagen 98,4 Prozent innerhalb von ±2 cm; der mittlere absolute Fehler betrug 0,23 cm. Von den 95 als nicht auswertbar markierten Stationsbildern wurden 92 automatisch abgelehnt.

Die ursprünglichen Stationsbilder und Trainingsdaten sind nicht Teil des Repositorys.

### Wo die Auswertung an Grenzen stößt

- Reale Trainingsbilder mit mehr als 25 cm Schnee fehlen bislang. Größere Schneehöhen wurden hauptsächlich an synthetischen Bildern geprüft.
- Tropfen, Schnee auf der Linse, Nebel und lokale Schmelzstellen können die Erkennung erschweren oder zu widersprüchlichen Ergebnissen führen.
- Eine neue, zeitlich spätere Bildserie wurde noch nicht unabhängig ausgewertet. Die bisherigen Ergebnisse beschreiben die Prüfung mit den vorhandenen Daten.

## Entwicklung

Die Windows-App wurde mit Python 3.12 gebaut und getestet. Für die Entwicklung auf Windows:

```powershell
git clone https://github.com/Dolcruz/schneepegel-brotenau.git
cd schneepegel-brotenau

py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.12.0 torchvision==0.27.0
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
```

### Kommandozeile

Ein oder mehrere Bilder lassen sich auch ohne Oberfläche auswerten:

```powershell
.\.venv\Scripts\python.exe -m height_model.predict_pipeline C:\Bilder\bild1.jpg C:\Bilder\bild2.jpg
```

Pro Bild wird eine JSON-Zeile ausgegeben. `status` beschreibt das Ergebnis, `snow_height_cm` die Schneehöhe und `reason` den Entscheidungsgrund:

```json
{"status": "measured", "snow_height_cm": 12.0, "reason": "positive_peg_model"}
{"status": "uncertain", "snow_height_cm": null, "reason": "geometric_models_disagree"}
{"status": "unusable", "snow_height_cm": null, "reason": "quality_filter"}
```

Beim ersten Aufruf lädt `torchvision` die vortrainierten ResNet-18-Gewichte herunter. Danach kann die Kommandozeilenauswertung ohne Internetverbindung laufen.

### Windows-Paket bauen

Mit der oben eingerichteten Umgebung:

```powershell
.\.venv\Scripts\python.exe build_windows.py
```

Das portable Programm liegt anschließend unter `dist/Schneepegel Brotenau`. Der Build lädt die ResNet-18-Gewichte herunter, prüft ihre Prüfsumme und packt alle benötigten Bibliotheken und Modelle dazu. Eine GPU wird nicht benötigt.

Nach dem Build lässt sich die Oberfläche auch mit `.\.venv\Scripts\python.exe schneepegel.py` aus dem Quellcode starten.

Für den Installer wird [Inno Setup 7](https://jrsoftware.org/isdl.php) benötigt:

```powershell
ISCC.exe installer.iss
```

Die Setup-Datei liegt unter `dist/installer`. Sie installiert die App unter `%LOCALAPPDATA%\Programs\Schneepegel Brotenau` und erstellt die Verknüpfungen sowie den Eintrag zur Deinstallation.

[Technische Hinweise und Prüfbericht zum Windows-Paket](https://github.com/Dolcruz/schneepegel-brotenau/releases/download/v1.0.0/Schneepegel_Brotenau_Technik.txt)

## Projektstruktur

```text
desktop/                     Oberfläche, Bildliste und lokale Speicherung
height_model/
  predict_pipeline.py        Auswertung und Kommandozeilen-Aufruf
  features.py                Kontext- und Pegelmerkmale
  geometric_meter.py         Pegelausrichtung und geometrische Messung
  artifacts/                 trainierte Höhenmodelle
  resources/                 Kalibrierung und Referenzpaket
quality_model/artifacts/     Modell zur Prüfung der Bildqualität
tests/                       Tests für Oberfläche, Speicherung und Verarbeitung
docs/                        Dokumentation zur Modellauswertung
build_windows.py             Paketbau für Windows
installer.iss                Windows-Installer
```
