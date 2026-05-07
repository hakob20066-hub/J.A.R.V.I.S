"""
MetadataExtractor — corrèle EXIF / stega / metadata déjà extraits.

Cross-référence GPS coords entre images, détecte device serial reuse.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field


@dataclass
class MetadataReport:
    gps_points:        list[dict] = field(default_factory=list)   # {lat, lon, source}
    devices_seen:      dict       = field(default_factory=dict)   # serial → count
    software_seen:     dict       = field(default_factory=dict)
    creators_seen:     dict       = field(default_factory=dict)
    stega_signals:     list[dict] = field(default_factory=list)
    serial_reuse:      list[dict] = field(default_factory=list)   # serial réutilisé

    def to_dict(self) -> dict:
        return {
            "gps_points":   self.gps_points[:100],
            "devices":      dict(list(self.devices_seen.items())[:30]),
            "software":     dict(list(self.software_seen.items())[:30]),
            "creators":     dict(list(self.creators_seen.items())[:30]),
            "stega_signals": self.stega_signals,
            "serial_reuse": self.serial_reuse,
        }


class MetadataExtractor:

    def analyze(self, findings: list) -> MetadataReport:
        rep = MetadataReport()
        if not findings:
            return rep

        device_counter: Counter = Counter()
        software_counter: Counter = Counter()
        creator_counter: Counter = Counter()
        serial_to_images: defaultdict = defaultdict(list)

        for f in findings:
            ftype = getattr(f, "type", "")
            source = getattr(f, "source", "")
            extracted = getattr(f, "extracted", {}) or {}

            # GPS
            lat = extracted.get("latitude") or extracted.get("GPSLatitude")
            lon = extracted.get("longitude") or extracted.get("GPSLongitude")
            try:
                if lat is not None and lon is not None:
                    rep.gps_points.append({
                        "lat": float(lat), "lon": float(lon),
                        "source": source,
                        "datetime": extracted.get("datetime") or extracted.get("DateTimeOriginal"),
                    })
            except (TypeError, ValueError):
                pass

            # Device
            for k in ("Make", "Model", "DeviceManufacturer", "DeviceModel"):
                v = extracted.get(k)
                if isinstance(v, str) and v.strip():
                    device_counter[f"{k}={v.strip()}"] += 1

            # Software
            for k in ("Software", "Creator", "Producer"):
                v = extracted.get(k)
                if isinstance(v, str) and v.strip():
                    software_counter[v.strip()] += 1

            # Creators / artist
            for k in ("Author", "Artist", "OwnerName", "Copyright"):
                v = extracted.get(k)
                if isinstance(v, str) and v.strip():
                    creator_counter[v.strip()] += 1

            # Serial number → potential reuse
            serial = extracted.get("SerialNumber") or extracted.get("BodySerialNumber")
            if isinstance(serial, str) and serial.strip():
                img = extracted.get("image") or extracted.get("file")
                serial_to_images[serial.strip()].append(img or source)

            # Stéganographie signals
            if ftype in ("stega_lsb", "stega_jpg_signature", "stega_hidden_data"):
                rep.stega_signals.append({
                    "type": ftype, "source": source,
                    "preview": str(extracted.get("raw") or extracted.get("info") or "")[:200],
                    "image": extracted.get("image"),
                })

        rep.devices_seen   = dict(device_counter)
        rep.software_seen  = dict(software_counter)
        rep.creators_seen  = dict(creator_counter)

        # Serial reuse : même serial sur >=2 images
        for serial, images in serial_to_images.items():
            if len(images) >= 2:
                rep.serial_reuse.append({"serial": serial, "images": images})

        return rep
