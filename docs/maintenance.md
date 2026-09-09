# Maintenance

How this repository is put together and how to work on it. For the episodes
themselves, see [the site](https://unpackthepcap.com/).

## Adding an episode

Create `episodes/<YYMMDD>-<Short-Title>/slides.md`, commit, push. That is the
whole process — the landing page rebuilds itself on every deploy and picks the
episode up. There is no episode list anywhere to keep in sync: not in this repo,
not in the README, not in the workflow.

Everything on the page is either read from the deck or detected from the files
beside it:

| Shown on the site | Comes from |
|:--|:--|
| Date | the `YYMMDD` prefix on the folder name |
| Episode number | chronological rank, oldest is 1 |
| Title | the deck's `# Unpack the PCAP: <title>` line |
| Subtitle | the `## <subtitle>` line under it |
| Slides link | always — the deck itself |
| 🧩 Zeek scripts | a non-empty `scripts/` folder exists |
| 📄 Transcript | `transcript.txt` exists |

Not every episode has every link, and that is fine: a missing file just means a
missing chip.

The only thing that cannot be detected is the video, since it lives on YouTube.
Add its id to the deck's frontmatter once the episode is up:

```yaml
---
theme: default
title: 'SmartApeSG ClickFix — Unidentified RAT → NetSupport RAT'
canvasWidth: 900
youtube: dQw4w9WgXcQ    # omit this line and the card shows "Video soon"
draft: true             # optional: build the deck but hide it from the site
---
```

Slidev ignores both keys, so they cost the deck nothing.

Episode numbers are derived from date order rather than stored, so publishing
episodes out of chronological order would renumber them. `draft: true` is
counted when numbering, so publishing a draft never renumbers the episodes
already out in the world.

## Working on the site locally

```bash
# Preview the landing page in a browser.
npm run preview:landing

# Screenshot it at phone, tablet, and desktop widths.
npm run shots:landing

# What would the page list? Writes nothing.
npm run check:landing
```

`preview:landing` builds to `/tmp/landing` and passes `--slides-base` so the
deck links point at the live site — the decks are not built locally, so relative
links would go nowhere.

`build:landing` writes `dist/` the way CI does, with relative deck links. That
only resolves if the decks have been built into `dist/` too, so it is mostly
useful for checking the generated markup.

### Screenshots

`npm run shots:landing` builds the page and writes five PNGs to
`output/screenshots/` — phone, phone light, tablet, desktop, desktop light — in
a few seconds. `output/` is gitignored, so they never get committed. They are
2x retina and the desktop shots run about 3 MB, which is deliberate: text stays
legible when you zoom in.

It is also a layout check, not just a picture-taker.
[tools/shoot-landing.js](../tools/shoot-landing.js) reports horizontal overflow
at every width and exits non-zero if any width scrolls sideways or the page
throws a JavaScript error. Horizontal overflow on a phone is the failure this
design exists to avoid, so it is worth running after any change to
`site/template.html`.

It uses the `playwright-chromium` that [tools/check-slides.sh](../tools/check-slides.sh)
already needs, so there is nothing extra to install. To shoot a page you built
somewhere else:

```bash
node tools/shoot-landing.js <path/to/index.html> <output-dir>
```

The page design — all markup and CSS — is [site/template.html](../site/template.html);
[tools/build_landing.py](../tools/build_landing.py) only fills in the episode
cards. Edit the template directly to restyle anything. The script uses the
standard library only, so CI needs no `pip install`.

## Search and paging

The landing page has a search box and, once there are enough episodes, a
"Show more" button. Both are progressive enhancements: every card is in the
HTML, so with JavaScript off the page is a plain complete list and the controls
hide themselves rather than sitting there dead.

- **Search** is always shown. It matches on title, subtitle, folder name,
  episode number, and both date spellings (`Jul 30, 2026` and `2026-07-30`), so
  `2035`, `ep 12`, and `qakbot 2040` all work. Every word must appear but order
  does not matter — `stealer lumma` and `lumma stealer` return the same
  episodes. `/` focuses the box, `Esc` clears it, and `?q=lumma` deep-links a
  search.
- **Paging** reveals `PAGE_SIZE` cards at a time and only appears above
  `SHOW_MORE_THRESHOLD`; both are constants at the top of
  [tools/build_landing.py](../tools/build_landing.py), currently 24. Below the
  threshold no button is emitted and every episode is on screen. Paging applies
  to search results too, so a broad query stays short.

The search haystack is built server-side by `search_haystack()`, which is why a
word that survives only in the folder name still matches. To make a new field
searchable, add it there.

### Why it scales

Measured on a generated 1000-episode set, 4x-throttled mobile CPU:

| | 1000 episodes |
|:--|--:|
| Generator runtime | 0.1 s |
| Page download, gzipped | 80 KB |
| First paint | 208 ms |
| Filter per keystroke | 3–7 ms |
| Page height, paged | 7 phone screens |
| Page height, unpaged | 252 phone screens |

Rendering was never the constraint; scroll length was, which is what paging
fixes. This approach holds to roughly 2000–3000 episodes. Past that the HTML
itself gets heavy and the answer changes to a JSON index with virtualized
rendering — at a weekly cadence, decades away.

### Two CSS traps

`.card` and `.more-wrap` both set `display`, which beats the browser's built-in
`[hidden] { display: none }`. Filtering works by toggling `hidden`, so
`.card[hidden]` and `.more-wrap[hidden]` rules are load-bearing — without them
hidden cards stay on screen. Anything else that gets filtered needs the same
treatment.

Placeholder substitution is a plain string replace, so a placeholder mentioned
twice in the template gets filled in twice — which silently duplicated the whole
card list once. `check_template()` now fails the build if a block placeholder
appears anything other than exactly once, which is why the template's own
comment spells the names without braces.

## Working on a deck

```bash
npx slidev episodes/<episode>/slides.md      # live preview
npm run check:slides episodes/<episode>      # find content running off a slide
```

[tools/check-slides.sh](../tools/check-slides.sh) exports the deck and checks it
for content that overflows the slide, which Slidev clips silently.

## Layout

```
episodes/<YYMMDD>-<Title>/
  slides.md        the deck; its frontmatter carries the episode metadata
  scripts/         Zeek scripts, if the episode has any    -> linked
  transcript.txt   if the episode has one                  -> linked
  pcaps/           capture files                           (not published)
site/template.html the landing page design
tools/
  build_landing.py   generates the landing page from episodes/
  shoot-landing.js   screenshots the landing page, checks for overflow
  check-slides.sh    exports a deck and checks it, wraps check_slides.py
  check_slides.py    finds content running off a slide
docs/
  maintenance.md     this file
  custom-domain.md   one-time runbook for the DNS move
output/            screenshots and Zeek logs           (gitignored)
```

## Deploying

[.github/workflows/deploy.yml](../.github/workflows/deploy.yml) runs on every push
to `main`: each deck is built to its own subdirectory of `dist/`, then
`tools/build_landing.py` writes the landing page to the site root. A malformed
episode folder name fails the build rather than silently disappearing from the
page.

### The domain

The site is served at [unpackthepcap.com](https://unpackthepcap.com/) as a
GitHub Pages custom domain. The domain itself is registered at DreamHost, but
DreamHost only answers DNS for it — nothing is hosted there. The step-by-step
setup, including the DreamHost panel clicks, is in
[custom-domain.md](custom-domain.md).

Nothing in the repo names the domain in a load-bearing way. `Setup Pages` runs
*before* the builds and reads the repo's live Pages settings, and both builds
take their URLs from its outputs:

| Output | On `github.io` | On the custom domain |
|:--|:--|:--|
| `base_path`, the deck `--base` prefix | `/UnpackThePCAP` | `` (empty) |
| `base_url`, the landing page's `--site-url` | `https://keithjjones.github.io/UnpackThePCAP` | `https://unpackthepcap.com` |

So the canonical and `og:` tags always match wherever the site is actually
being served, and pointing the site at a different domain is a change in repo
Settings → Pages, not a change here. That prefix matters: deck assets are
absolute URLs, so a deck built with the wrong `--base` loads a blank page.

`www.unpackthepcap.com` is not configured anywhere and does not need to be. The
custom domain is set to the bare apex, and GitHub redirects the `www` variant to
it: per GitHub's docs, "if you instead configure `example.com` as the custom
domain, then `www.example.com` will redirect to `example.com`." That redirect is
conditional on the `www` DNS record existing, which is the only reason it is in
the record list below. Everything in this repo links to the apex.

If the domain is ever moved, the DNS side is four A records and four AAAA
records on the apex plus a `www` CNAME to `keithjjones.github.io` — see
[GitHub's apex domain docs](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site)
for the current addresses. Four things that are easy to get wrong:

- DreamHost will not let you set apex A records while the domain is Fully
  Hosted. It has to be **DNS Only** first, which also means removing the old
  `.htaccess` redirect, since there is no longer a web host to run it.
- The `www` CNAME points at `keithjjones.github.io`, **not** at
  `unpackthepcap.com`. GitHub's docs warn that if a custom subdomain references
  the apex domain "you will encounter issues with enforcing HTTPS to your
  website," because the certificate is issued per name.
- If any `CAA` records exist on the domain, one of them must allow
  `letsencrypt.org` or HTTPS will never provision. There are currently none,
  which is fine — no CAA record means any CA may issue.
- Because this deploys through GitHub Actions rather than a `gh-pages` branch,
  **no `CNAME` file is involved.** GitHub's docs are explicit that for Actions
  deployments "no `CNAME` file is created, and any existing `CNAME` file is
  ignored and is not required." Don't add one to `dist/` expecting it to do
  something.

`--site-url` is still a flag on [tools/build_landing.py](../tools/build_landing.py),
defaulting to the custom domain, which is what the local `preview:landing` and
`shots:landing` scripts use for their deck links.
