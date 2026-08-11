# Schneepegelauswertung Brotenau

Dieses Repository enthält die lauffähige Auswertung für die fest installierte Kamera am Schneepegel Brotenau. Ein Bild wird eingelesen und als Schneehöhe, unsicher oder nicht auswertbar zurückgegeben.

Das Modell ist für diese Kamera, diesen Blickwinkel und diesen Pegel kalibriert. Es ist kein allgemeiner Schneedetektor für andere Standorte.

## Schnellstart unter Windows

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
.\.venv\Scripts\python.exe height_model\predict_pipeline.py C:\Pfad\zum\bild.jpg
```

Mehrere Bilder können in einem Aufruf übergeben werden:

```powershell
.\.venv\Scripts\python.exe height_model\predict_pipeline.py C:\Bilder\bild1.jpg C:\Bilder\bild2.jpg
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

Der aktuelle Stand ist damit für einen kontrollierten Pilotbetrieb an dieser Installation geeignet. Die Werte sind kein Nachweis für andere Kameras oder Standorte.

## Bekannte Grenzen

- Reale Trainingsbilder über 25 cm fehlen bisher. Größere Höhen wurden hauptsächlich mit synthetischen Bildern geprüft.
- Tropfen, Schnee auf der Linse, Nebel und lokale Schmelzstellen können Pegel und Umgebung widersprüchlich erscheinen lassen.
- Eine deutliche Änderung der Kamera oder des Pegels erfordert eine neue Kalibrierung.
- Eine vollständig neue, zeitlich spätere Bildserie wurde noch nicht als unabhängiger Zukunftstest ausgewertet.

## Wenn neue Bilder hinzukommen

1. Originalbild, Modellausgabe und gegebenenfalls die manuell geprüfte Schneehöhe gemeinsam speichern.
2. Unsichere Bilder, offensichtliche Fehler und eine kleine Zufallsstichprobe korrekter Messungen nachprüfen.
3. Mindestens eine komplette neue Zeitserie unangetastet als Zukunftstest zurückhalten.
4. Erst bei wiederkehrenden Fehlermustern nachtrainieren und das neue Modell anschließend wieder gegen den zurückgehaltenen Test prüfen.

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

