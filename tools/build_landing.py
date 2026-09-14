#!/usr/bin/env python3
"""Generate the site landing page from the episodes/ directory.

Adding an episode means creating episodes/<YYMMDD>-<Slug>/slides.md. There is
no central list to keep in sync -- everything on the landing page is either
read out of the deck or detected from the files next to it:

    date            the YYMMDD prefix on the folder name
    episode number  chronological rank, oldest episode is 1
    title           the deck's "# Unpack the PCAP: <title>" line
    subtitle        the "## <subtitle>" line under it
    slides link     always, because the deck is what we just built
    Zeek scripts    scripts/ exists and has files in it
    transcript      transcript.txt exists

The one thing that cannot be detected is the YouTube video, because it lives
on YouTube. Put the id in the deck's frontmatter once the episode is up:

    ---
    theme: default
    title: 'SmartApeSG ClickFix -- Unidentified RAT -> NetSupport RAT'
    youtube: dQw4w9WgXcQ    # omit until the video is published
    draft: true             # optional: hide from the landing page entirely
    ---

Slidev ignores both keys (verified against @slidev/cli 52), so they cost the
deck nothing.

Usage:
    python3 tools/build_landing.py                      # -> dist/
    python3 tools/build_landing.py --out /tmp/preview    # somewhere else
    python3 tools/build_landing.py --check               # just list what it found
    python3 tools/build_landing.py --find 3              # ep number -> folder
    python3 tools/build_landing.py --find 260623-Click   # folder -> ep number

Episode numbers live nowhere but this file's ordering, so --find is how you ask
what they are rather than counting folders by hand.

Exits 1 if an episode folder is malformed, so a bad name fails the build
rather than silently vanishing from the page.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Only a default: CI passes --site-url from the repo's live Pages settings, so
# the canonical and og: tags always match wherever the site is actually served.
DEFAULT_SITE_URL = "https://unpackthepcap.com/"
FALLBACK_REPO_URL = "https://github.com/keithjjones/UnpackThePCAP"
BANNER_SRC = REPO_ROOT / "images" / "Unpack the PCAP.png"

# episodes/260623-ClickFix-Unknown-RAT-Netsupport
SLUG_RE = re.compile(r"^(\d{2})(\d{2})(\d{2})-(.+)$")

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# How many cards the page reveals at a time, and the count above which a
# "Show more" button is worth having at all. Below the threshold every episode
# is on screen and the button is never emitted.
PAGE_SIZE = 24
SHOW_MORE_THRESHOLD = 24

# "# Unpack the PCAP: SmartApeSG ClickFix" -> "SmartApeSG ClickFix"
TITLE_PREFIX_RE = re.compile(r"^Unpack the PCAP:\s*", re.IGNORECASE)

# A bare "key: value" line in the deck's headmatter. Enough for the scalars we
# read; deliberately not a YAML parser, so this needs no third-party module on
# the CI runner.
YAML_SCALAR_RE = re.compile(r"^([A-Za-z_][\w.\-]*)\s*:\s*(.*)$")

# Straight quote pairs -> curly, for display only. The decks type "..." and a
# web page should not.
SMART_QUOTES_RE = re.compile(r'"([^"]+)"')


# --------------------------------------------------------------------------
# Episode discovery
# --------------------------------------------------------------------------

@dataclass
class Episode:
    slug: str
    year: int
    month: int
    day: int
    title: str
    subtitle: str
    youtube: str = ""
    draft: bool = False
    has_scripts: bool = False
    has_transcript: bool = False
    number: int = 0  # assigned after sorting

    @property
    def sort_key(self) -> tuple[int, int, int, str]:
        return (self.year, self.month, self.day, self.slug)

    @property
    def date_display(self) -> str:
        return f"{MONTHS[self.month - 1]} {self.day}, {self.year}"

    @property
    def date_iso(self) -> str:
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"


def parse_headmatter(text: str) -> dict[str, str]:
    """Read the leading `---` block of a slides.md into a flat dict of strings."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    out: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = YAML_SCALAR_RE.match(line)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        # Strip a trailing comment, but only when it is clearly one ( " #" ),
        # so a value containing a hash survives.
        value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key] = value
    return out


def parse_headings(text: str) -> tuple[str, str]:
    """Pull the title from the deck's first `#` line and subtitle from the `##` after it."""
    title = subtitle = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not title:
            if stripped.startswith("# "):
                title = TITLE_PREFIX_RE.sub("", stripped[2:].strip())
            continue
        # Only the ## immediately following the title, before any other content.
        if stripped.startswith("## "):
            subtitle = stripped[3:].strip()
            break
        if stripped and not stripped.startswith("<!--"):
            break
    return title, subtitle


def is_truthy(value: str) -> bool:
    return value.strip().lower() in {"true", "yes", "1", "on"}


def load_episode(directory: Path, errors: list[str]) -> Episode | None:
    """Build an Episode from one episodes/<slug>/ directory, or record why not."""
    match = SLUG_RE.match(directory.name)
    if not match:
        errors.append(
            f"{directory.name}: folder name must start with YYMMDD-, e.g. 260623-My-Title"
        )
        return None

    deck = directory / "slides.md"
    if not deck.is_file():
        errors.append(f"{directory.name}: no slides.md")
        return None

    yy, mm, dd, _ = match.groups()
    month, day = int(mm), int(dd)
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        errors.append(f"{directory.name}: '{yy}{mm}{dd}' is not a valid YYMMDD date")
        return None

    text = deck.read_text(encoding="utf-8")
    headmatter = parse_headmatter(text)
    title, subtitle = parse_headings(text)

    if not title:
        # Fall back to the frontmatter title, split on an em dash if present,
        # so a deck without the usual "# / ##" pair still renders sensibly.
        raw = headmatter.get("title", "")
        if not raw:
            errors.append(f"{directory.name}: no '# ' heading and no frontmatter title")
            return None
        parts = re.split(r"\s+[—-]{1,2}\s+", raw, maxsplit=1)
        title = TITLE_PREFIX_RE.sub("", parts[0].strip())
        subtitle = parts[1].strip() if len(parts) > 1 else ""

    scripts_dir = directory / "scripts"

    return Episode(
        slug=directory.name,
        year=2000 + int(yy),
        month=month,
        day=day,
        title=title,
        subtitle=subtitle,
        youtube=headmatter.get("youtube", ""),
        draft=is_truthy(headmatter.get("draft", "")),
        has_scripts=scripts_dir.is_dir() and any(scripts_dir.iterdir()),
        has_transcript=(directory / "transcript.txt").is_file(),
    )


def discover(episodes_dir: Path) -> tuple[list[Episode], list[str]]:
    """Every episode, newest first, numbered. Drafts included and flagged.

    Drafts stay in the list because they hold a number, and callers that need to
    look one up want the draft they are working on. The page filters them out.
    """
    errors: list[str] = []
    found: list[Episode] = []

    for directory in sorted(p for p in episodes_dir.iterdir() if p.is_dir()):
        episode = load_episode(directory, errors)
        if episode is not None:
            found.append(episode)

    # Number oldest-first, including drafts, so publishing a draft does not
    # renumber the episodes already out in the world.
    found.sort(key=lambda e: e.sort_key)
    for index, episode in enumerate(found, start=1):
        episode.number = index

    # Present newest first: that is what a visitor wants to see at the top.
    return list(reversed(found)), errors


# A bare number, with or without an "ep" in front: "3", "ep3", "EP 12". Bounded
# to four digits so a YYMMDD date falls through to the slug match below, where
# "260904" finds the episode by its folder name instead.
EP_QUERY_RE = re.compile(r"^(?:ep\s*)?(\d{1,4})$", re.IGNORECASE)


def find_episodes(episodes: list[Episode], query: str) -> list[Episode]:
    """Resolve a query in either direction: episode number, or folder name."""
    query = query.strip().rstrip("/")

    match = EP_QUERY_RE.match(query)
    if match:
        numbered = [e for e in episodes if e.number == int(match.group(1))]
        # No such episode, so the digits were not a number after all: "260" is
        # someone reaching for a date. Fall through and match it as a name.
        if numbered:
            return numbered

    # A path, a bare folder name, or any fragment of one. Taking the basename
    # means "episodes/260623-Foo" and a tab-completed absolute path both work.
    name = Path(query).name.lower()
    exact = [e for e in episodes if e.slug.lower() == name]
    return exact or [e for e in episodes if name in e.slug.lower()]


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def smarten(text: str) -> str:
    """Curl straight quote pairs and normalise the arrow, for display."""
    text = SMART_QUOTES_RE.sub("“\\1”", text)
    return text.replace("->", "→")


def esc(text: str) -> str:
    return html.escape(smarten(text), quote=True)


def render_chip(kind: str, label: str, href: str) -> str:
    return (f'<li><a class="chip chip-{kind}" href="{html.escape(href, quote=True)}">'
            f'<span class="dot"></span>{html.escape(label)}</a></li>')


def search_haystack(episode: Episode) -> str:
    """Everything a visitor might plausibly type to find this episode.

    Includes the folder slug, so a word that survives only in the directory name
    still matches, and both date spellings so "2026-07" and "Jul 2026" work.
    """
    parts = [
        episode.title,
        episode.subtitle,
        episode.slug.replace("-", " "),
        f"ep {episode.number}",
        f"episode {episode.number}",
        episode.date_display,
        episode.date_iso,
    ]
    return " ".join(parts).lower()


def render_card(episode: Episode, slides_base: str, repo_url: str) -> str:
    deck_url = f"{slides_base}{episode.slug}/"
    tree = f"{repo_url}/tree/main/episodes/{episode.slug}"
    blob = f"{repo_url}/blob/main/episodes/{episode.slug}"

    # The title goes to the video, which is what someone clicking an episode is
    # after; the deck has its own chip below. Until the video is up there is
    # nothing to link to, so the title falls back to the deck.
    title_url = f"https://youtu.be/{episode.youtube}" if episode.youtube else deck_url

    chips = []
    if episode.youtube:
        chips.append(render_chip("video", "Video", f"https://youtu.be/{episode.youtube}"))
    chips.append(render_chip("slides", "Slides", deck_url))
    if episode.has_scripts:
        chips.append(render_chip("scripts", "Zeek scripts", f"{tree}/scripts"))
    if episode.has_transcript:
        chips.append(render_chip("txt", "Transcript", f"{blob}/transcript.txt"))
    if not episode.youtube:
        # Better than an empty gap: says the episode is out, video is pending.
        chips.append('<li><span class="chip muted"><span class="dot"></span>Video soon</span></li>')

    subtitle = f'\n          <p class="subtitle">{esc(episode.subtitle)}</p>' if episode.subtitle else ""
    chip_html = "\n          ".join(chips)

    return f'''      <li class="card" data-search="{html.escape(search_haystack(episode), quote=True)}">
        <div class="stripe"></div>
        <div class="card-body">
          <p class="meta">
            <span class="ep-num">EP {episode.number}</span>
            <time class="date" datetime="{episode.date_iso}">{episode.date_display}</time>
          </p>
          <h3><a href="{html.escape(title_url, quote=True)}">{esc(episode.title)}</a></h3>{subtitle}
        </div>
        <ul class="links">
          {chip_html}
        </ul>
      </li>'''


def render_show_more(total: int) -> str:
    """The "Show more" button, or nothing when every episode already fits."""
    if total <= SHOW_MORE_THRESHOLD:
        return ""
    # hidden by default: the script unhides it, so with JS off the full list is
    # on screen and a button that cannot work is never shown.
    return ('    <div class="more-wrap" id="more-wrap" hidden>\n'
            '      <button class="show-more" id="show-more" type="button">Show more</button>\n'
            '    </div>')


# Placeholders that stand for a block of markup, so a stray second mention
# anywhere in the template -- a comment documenting it, say -- would emit that
# block twice. SITE_URL is deliberately repeated (og:image, og:url, canonical),
# so it is only required to appear at all.
UNIQUE_PLACEHOLDERS = ("EPISODES", "COUNT", "PAGE_SIZE", "SHOW_MORE")
REPEATED_PLACEHOLDERS = ("SITE_URL",)


def check_template(template: str) -> None:
    """Fail early if the template's placeholders are not as substitution expects."""
    for name in UNIQUE_PLACEHOLDERS:
        seen = template.count("{{" + name + "}}")
        if seen != 1:
            raise SystemExit(
                f"build_landing: template has {seen} copies of "
                f"{{{{{name}}}}}, expected exactly 1"
            )
    for name in REPEATED_PLACEHOLDERS:
        if "{{" + name + "}}" not in template:
            raise SystemExit(f"build_landing: template is missing {{{{{name}}}}}")


def render_page(template: str, episodes: list[Episode], *,
                slides_base: str, repo_url: str, site_url: str) -> str:
    check_template(template)
    cards = "\n".join(render_card(e, slides_base, repo_url) for e in episodes)
    total = len(episodes)
    count = f"{total} unpacked"
    # Below the threshold there is nothing to page, so reveal everything at once.
    page_size = PAGE_SIZE if total > SHOW_MORE_THRESHOLD else total
    return (template
            .replace("{{EPISODES}}", cards)
            .replace("{{COUNT}}", count)
            .replace("{{PAGE_SIZE}}", str(page_size))
            .replace("{{SHOW_MORE}}", render_show_more(total))
            .replace("{{SITE_URL}}", site_url))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def describe(episode: Episode) -> str:
    """Two lines: what the card will say, then the folder it came from.

    The folder name is on its own line rather than a fourth column because it is
    longer than everything else put together, and it is what makes this listing
    readable in both directions -- number to folder and folder to number.
    """
    extras = [name for flag, name in
              ((episode.youtube, "video"), (episode.has_scripts, "scripts"),
               (episode.has_transcript, "transcript")) if flag]
    draft = "  (draft, hidden from the site)" if episode.draft else ""
    return (f"  EP {episode.number}  {episode.date_iso}  {episode.title}"
            f"  [{', '.join(extras) or 'slides only'}]{draft}\n"
            f"        episodes/{episode.slug}")


def repo_url_from_package_json() -> str:
    """Reuse package.json's repository URL rather than duplicating it here."""
    try:
        data = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
        url = data.get("repository", {}).get("url", "")
    except (OSError, ValueError):
        return FALLBACK_REPO_URL
    url = re.sub(r"^git\+", "", url)
    url = re.sub(r"\.git$", "", url)
    return url or FALLBACK_REPO_URL


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "dist",
                        help="output directory for index.html (default: dist/)")
    parser.add_argument("--episodes", type=Path, default=REPO_ROOT / "episodes",
                        help="directory of episode folders")
    parser.add_argument("--template", type=Path, default=REPO_ROOT / "site" / "template.html",
                        help="page template")
    parser.add_argument("--site-url", default=DEFAULT_SITE_URL,
                        help="canonical site URL, used for the share and canonical tags")
    parser.add_argument("--slides-base", default="",
                        help="prefix for deck links; default is relative, which is what the "
                             "deployed site wants. Pass the live site URL to preview locally.")
    parser.add_argument("--check", action="store_true",
                        help="report what was found and write nothing")
    parser.add_argument("--find", metavar="EP-OR-DIR",
                        help="look up one episode by number ('3') or by folder "
                             "name ('260623-ClickFix...', a path, or a fragment) "
                             "and write nothing")
    args = parser.parse_args(argv)

    if not args.site_url.endswith("/"):
        args.site_url += "/"

    if not args.episodes.is_dir():
        print(f"build_landing: no episodes directory: {args.episodes}", file=sys.stderr)
        return 1

    episodes, errors = discover(args.episodes)
    for message in errors:
        print(f"build_landing: {message}", file=sys.stderr)
    if errors:
        return 1

    if args.find:
        hits = find_episodes(episodes, args.find)
        if not hits:
            print(f"build_landing: no episode matches {args.find!r}", file=sys.stderr)
            return 1
        for episode in hits:
            print(describe(episode))
        return 0

    for episode in episodes:
        print(describe(episode))

    if args.check:
        return 0

    published = [e for e in episodes if not e.draft]
    if not published:
        print("build_landing: no publishable episodes found", file=sys.stderr)
        return 1

    repo_url = repo_url_from_package_json()
    page = render_page(args.template.read_text(encoding="utf-8"), published,
                       slides_base=args.slides_base, repo_url=repo_url,
                       site_url=args.site_url)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "index.html").write_text(page, encoding="utf-8")

    images = args.out / "images"
    images.mkdir(exist_ok=True)
    shutil.copyfile(BANNER_SRC, images / "banner.png")

    print(f"build_landing: wrote {args.out / 'index.html'} ({len(published)} episodes)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
