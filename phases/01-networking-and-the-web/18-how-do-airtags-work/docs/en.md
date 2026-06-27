# How do AirTags work?

> A billion iPhones act as anonymous relays so you can find your keys — and no one, not even Apple, can see your location data.

**Type:** Learn
**Prerequisites:** Bluetooth and BLE basics, Public-key cryptography overview, How DNS works
**Time:** ~18 minutes

---

## The Problem

You drop your keys behind the couch cushion. You leave your bag on a train. Your luggage ends up at the wrong airport. Without a reliable way to locate physical objects, your only option is to retrace your steps and hope for the best.

GPS trackers solve this in open sky, but they fail indoors, drain batteries in hours, and require cellular data plans. Wi-Fi-based finders need you to be in range of a known network. Neither approach scales to everyday items in a dense city.

What you actually need is a tracking system that works indoors and outdoors, requires no data plan, has year-long battery life, and covers almost every place a human might leave a lost object. The only way to build that is to crowd-source it — and crowd-sourcing location data at scale raises serious privacy questions that must be answered at the cryptographic level, not the policy level.

AirTags solve exactly this: they turn a billion iPhones into a silent, anonymized relay network while ensuring that neither the relaying iPhone nor Apple itself can read your location data.

---

## The Concept

### The Four Layers of an AirTag

An AirTag combines four distinct hardware/protocol layers, each with a different range and purpose:

| Layer | Technology | Range | Purpose |
|---|---|---|---|
| Discovery beacon | Bluetooth LE (BLE) | ~100 m | Lets nearby Apple devices detect the AirTag |
| Crowdsourced relay | Find My network (BLE + iCloud) | Global | Relays location to owner via iCloud |
| Precision Finding | Ultra-Wideband (UWB / U1 chip) | ~10 m | Sub-meter directional guidance |
| Lost Mode tap | NFC | <5 cm | Any phone reads contact URL without an app |

### The Find My Network — The Core Mechanism

Apple's Find My network is the engine. Every iPhone, iPad, and Mac running iOS 14.5+ or macOS 11.3+ participates automatically, without the owner opting in or out. When any of these devices spots an AirTag's BLE advertisement, it silently does three things:

1. Records its own GPS coordinates at that moment.
2. Encrypts those coordinates using the AirTag's **rotating public key**.
3. Uploads the encrypted blob (plus a hash of the public key) to Apple's servers.

The device does this in a background thread, consuming negligible battery, and the whole transaction is invisible to its owner.

```
AirTag (BLE broadcast)
    │  advertises rotating public key P_i
    ▼
Passing iPhone (relay)
    │  reads P_i
    │  encrypts (GPS_lat, GPS_lon) with P_i  →  ciphertext C
    │  computes SHA256(P_i)                  →  report_id
    │  uploads { report_id, C, timestamp } to Apple iCloud
    ▼
Apple iCloud (blind relay)
    │  stores { report_id, C, timestamp }
    │  Apple cannot decrypt C — it only holds ciphertext
    ▼
Owner's iPhone (Find My app)
    │  knows all derived private keys d_i for this AirTag
    │  requests reports matching SHA256(P_i) for each key rotation
    │  decrypts C → (GPS_lat, GPS_lon)
    │  displays location on map
```

### Public-Key Privacy Architecture

The privacy design uses **offline-finding** cryptography based on Elliptic Curve Diffie-Hellman (ECDH):

1. **Key generation at pairing time.** When you pair an AirTag, your iPhone generates a master secret key and derives a long sequence of key pairs `(d_0, P_0), (d_1, P_1), …`. Private keys `d_i` stay on your device and iCloud Keychain. Public keys `P_i` are loaded onto the AirTag.

2. **Key rotation.** The AirTag rotates to the next public key `P_i` roughly every 15 minutes. It also randomizes its Bluetooth MAC address on each rotation. This prevents a third-party (e.g., a store camera tracking customers by their Bluetooth signal) from correlating successive broadcasts.

3. **Encryption by the relay.** The passing iPhone encrypts the location with `P_i`. Only the holder of the matching private key `d_i` can decrypt it. The relay iPhone never learns whose AirTag it just saw, and Apple stores only ciphertext it cannot read.

4. **Owner decryption.** The Find My app derives the same sequence of public keys locally, computes their hashes, requests matching reports from Apple, and decrypts each with the stored private key.

This is why AirTags have stronger privacy guarantees than most commercial trackers: the guarantee is cryptographic, not contractual.

### Ultra-Wideband Precision Finding

Once you are within roughly 10 meters, Precision Finding activates. Your iPhone's U1 chip uses **Ultra-Wideband (UWB)** — a radio technology that measures time-of-flight of pulses at sub-nanosecond resolution. Because `distance = (speed of light) × (time of flight)`, UWB can measure distance to ±10 cm and bearing to a few degrees.

The Find My app overlays this with the device's ARKit camera feed, accelerometer, and gyroscope to give you an arrow pointing directly at the AirTag, a distance readout, and haptic feedback that intensifies as you get closer. This is qualitatively different from RSSI-based proximity: RSSI tells you "approximately here"; UWB tells you "it is behind that couch cushion, 0.4 m to your left."

### Lost Mode and NFC

If an AirTag is lost and a stranger finds it, they can tap it with any NFC-capable smartphone — Android included. The AirTag responds with a URL like `found.apple.com/?pid=<tag_id>`. Opening the URL in a browser shows whatever contact information the owner configured. No app required, no Apple account required. This is the lowest-friction lost-and-found handoff available on consumer hardware.

---

## Build It / In Depth

### Walkthrough: End-to-End Location Report

Let's trace a single location report from the moment the AirTag broadcasts to the moment you see a pin on a map.

**T=0 — Broadcast**

The AirTag wakes from deep sleep, emits a BLE advertisement frame at 1 Hz containing the current public key `P_i` encoded in the manufacturer-specific data field, then sleeps again. Battery draw: ~0.03 mA average.

**T+0.01 s — Detection by relay**

A stranger's iPhone 13 walking past receives the advertisement. The Find My background daemon on iOS:

```
1. Parses P_i from the BLE frame.
2. Generates an ephemeral ECDH key pair (e_priv, e_pub).
3. Computes shared_secret = ECDH(e_priv, P_i).
4. Derives encryption_key = HKDF(shared_secret, "find-my-location", 32).
5. Encrypts payload:
     payload = AES-GCM-256(
       key      = encryption_key,
       nonce    = random_96_bit,
       plaintext = (lat, lon, accuracy, timestamp)
     )
6. Builds report:
     {
       "hashed_adv_key": SHA256(P_i)[0:10],   // 10-byte prefix for lookup
       "encrypted_location": payload,
       "e_pub": e_pub,                          // needed for owner decryption
       "timestamp": unix_epoch_ms
     }
7. Queues report for upload to Apple over HTTPS (batched with other reports).
```

**T+~60 s — Upload to iCloud**

The relay iPhone batches reports and sends them over HTTPS to `gateway.icloud.com/acsnservice/find`. Apple indexes them by `hashed_adv_key`. Apple cannot decrypt `encrypted_location`.

**T+~2–5 min — Owner poll**

The Find My app polls for new reports. It sends Apple the set of `hashed_adv_key` values for the current key rotation windows of all tracked items. Apple returns matching encrypted blobs.

**T+~2–5 min — Decryption on device**

```
For each returned report:
  e_pub           <- from report
  d_i             <- private key for the matching rotation window
  shared_secret   = ECDH(d_i, e_pub)
  encryption_key  = HKDF(shared_secret, "find-my-location", 32)
  (lat, lon, ...) = AES-GCM-256-decrypt(encryption_key, payload)
```

The decrypted GPS coordinates are now shown on the map. Apple handled the relay but never held a decryptable location.

### Anti-Stalking: Unwanted Tracking Alerts

Apple baked in two defenses against using AirTags to covertly track people:

1. **Sound alert.** An AirTag separated from its owner's iPhone for 8–24 hours (the window is randomized to prevent gaming it) plays an audible beep from its internal speaker.

2. **iPhone notification.** Any iPhone running iOS 14.5+ that detects an AirTag traveling with it over time — but not paired to that phone — receives a "AirTag found moving with you" notification. The user can play a sound on the AirTag and see its serial number.

3. **Android.** Apple released an Android app ("Tracker Detect") that does the same scan on demand, though without the continuous background scanning available on iOS.

---

## Use It

### Where Each Layer Matters in Real Deployments

| Scenario | Dominant layer | Why |
|---|---|---|
| Lost bag in airport terminal | Find My network (BLE relay) | Dense iPhone population; GPS indoors unreliable |
| Keys dropped in your own apartment | UWB Precision Finding | Close-range, sub-meter needed |
| Luggage left in another city | Find My network | Long-range, asynchronous relay |
| Stranger finds lost item | NFC Lost Mode | No Apple device or account required |
| Bike parked outdoors | Find My network + GPS from relay iPhone | Works as long as one iPhone walks nearby |

### Apple Find My vs. Competitors

| Feature | Apple AirTag | Tile | Samsung SmartTag 2 | Chipolo |
|---|---|---|---|---|
| Network size | ~1 B Apple devices | ~35 M Tile app users | Samsung Galaxy devices | Chipolo app users |
| Encryption | ECDH end-to-end | Proprietary, not E2E | Proprietary | Not E2E |
| UWB Precision | Yes (U1) | No | Yes (Galaxy only) | No |
| Battery life | ~1 year (CR2032) | 1–3 years | ~6 months | ~2 years |
| Cross-platform | NFC Lost Mode on Android | Full Android support | Android (SmartThings) | Android app |
| Anti-stalking | iOS + Android alerts | Alerts (delayed) | Galaxy alerts | App alerts |

### When Find My Has Blind Spots

The network degrades gracefully but has real limits:

- **Rural areas:** Low iPhone density means reports arrive infrequently. A bag lost in a national park may not be locatable until a hiker passes by.
- **Faraday cages:** Metal containers (car trunks, steel shipping containers) attenuate BLE significantly.
- **Indoor accuracy:** Relay iPhones use GPS, which can be off by 10–30 m inside buildings. The map pin is an approximation of where the relay phone was, not a floor plan coordinate.
- **Key rotation lag:** If a relay iPhone caches the wrong key rotation window, its report may not match any owner query until the next poll.

---

## Common Pitfalls

- **Confusing "last seen location" with real-time location.** An AirTag does not ping Apple on demand. The map shows the most recent report, which could be hours old. If your item is not moving and is in a low-density area, the pin will not update.

- **Assuming AES-GCM protects the BLE layer.** The BLE broadcast itself is not encrypted — any Bluetooth scanner can see the raw advertisement frame and capture the rotating public key. What prevents misuse is that the public key alone is useless: you cannot decrypt past reports, and the key rotates before meaningful tracking is possible.

- **Forgetting that UWB requires an iPhone 11 or later.** On older iPhones, Precision Finding falls back to audio-only (a beep from the speaker) and Bluetooth RSSI signal strength bars — far less precise. Do not promise sub-meter accuracy to users on older devices.

- **Battery life varies with relay density.** In high-density urban environments, the AirTag's BLE radio is detected and woken more often. Battery life can drop toward 6–8 months in very high-traffic locations (airport check-in zones). Apple's stated "one year" is an average, not a guarantee.

- **Lost Mode does not broadcast GPS to strangers.** Some users expect that enabling Lost Mode makes the AirTag broadcast its GPS location over Bluetooth. It does not. Lost Mode simply marks the item as lost in Apple's system, adds contact info to the NFC tap URL, and lets you receive a notification when the next relay report arrives. The security model does not change.

---

## Exercises

1. **Easy — Trace the key rotation.** An AirTag rotates its public key every 15 minutes. Over a 24-hour period, how many distinct `hashed_adv_key` values will Apple receive for a single AirTag? What is the minimum number of private keys the owner's device must store to decrypt all reports from the last 7 days?

2. **Medium — Design a relay budget.** Estimate the data cost (in bytes per day) imposed on a relay iPhone in a city where it detects 20 AirTags per hour. Assume each encrypted report is ~100 bytes and reports are batched hourly. How does this change if Apple moves to a push model where the AirTag initiates the upload?

3. **Hard — Extend the privacy model.** The current scheme prevents Apple from reading locations. Design a protocol change that would also prevent Apple from inferring the owner's identity even if Apple correlates `hashed_adv_key` values across time windows. Hint: consider how the key derivation schedule could be made unknowable to Apple without breaking the owner's ability to query for reports.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Find My network | Apple's internal GPS tracking system | A crowdsourced network of Apple devices that anonymously relay Bluetooth pings from AirTags to iCloud |
| Rotating key | A security gimmick | A cryptographic mechanism that changes the AirTag's advertised public key every ~15 minutes to prevent cross-device tracking by third parties |
| Precision Finding | Better GPS | Time-of-flight Ultra-Wideband ranging (U1 chip) giving sub-meter distance and directional guidance — nothing to do with GPS |
| Offline finding | The AirTag goes offline | The relay iPhone has no knowledge of whose AirTag it is relaying ("offline" refers to the tag being out of the owner's Bluetooth range, not the network) |
| Lost Mode | The AirTag sends out an SOS | It flags the item as lost in Apple's database and populates the NFC tap URL with contact info; the underlying relay mechanism is unchanged |
| RSSI | Accurate distance measurement | Received Signal Strength Indication — a noisy proxy for distance that varies with obstacles, reflections, and orientation by ±10 m or more |
| NFC tap | Requires the Apple ecosystem | Any NFC-capable smartphone (iOS or Android) can tap a lost AirTag and open the contact URL in a standard web browser — no app required |

---

## Further Reading

- [Apple Platform Security — Find My Network](https://support.apple.com/guide/security/find-my-network-sec60fd770c8/web) — Apple's official documentation on the cryptographic design of the Find My protocol.
- [Who Can Find My Devices? A Security and Privacy Analysis of Apple's Crowd-Sourced Bluetooth Location Tracking System](https://www.usenix.org/conference/usenixsecurity21/presentation/heinrich) — USENIX Security 2021 paper by Heinrich et al.; the most rigorous independent analysis of the Find My privacy model.
- [Apple's Ultra Wideband Technology Overview](https://developer.apple.com/documentation/nearbyinteraction) — Developer documentation for the Nearby Interaction framework that exposes UWB ranging to third-party apps, with architecture context.
- [Bluetooth Core Specification 5.x — Advertising and Scanning](https://www.bluetooth.com/specifications/specs/core-specification-5-4/) — The upstream spec for how BLE advertisements work, including privacy address rotation (directly analogous to AirTag's rotating MAC).
- [OpenHaystack — Reverse-engineered Find My protocol](https://github.com/seemoo-lab/openhaystack) — Open-source project from TU Darmstadt that reverse-engineered the Find My network; the accompanying academic paper is the best public description of the wire protocol.
