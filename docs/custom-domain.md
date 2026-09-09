# Moving the site to unpackthepcap.com

A one-time runbook for pointing `unpackthepcap.com` at GitHub Pages instead of
redirecting to it. Follow it top to bottom — the ordering matters in one place
(step 6) and there is a prerequisite that is easy to miss (step 2).

Once this is done, the permanent notes live in
[maintenance.md → The domain](maintenance.md#the-domain), and this file can go.

## Starting state

Observed before any changes were made:

| | |
|:--|:--|
| `unpackthepcap.com` → | `69.163.176.199` (DreamHost, Apache) |
| `www.unpackthepcap.com` → | **does not exist** (`NXDOMAIN`) |
| Both currently | `301` to `https://github.com/keithjjones/UnpackThePCAP` |
| Nameservers | `ns1/ns2/ns3.dreamhost.com` |
| TTL | 60 seconds, so DNS changes land in minutes |
| CAA records | none, on either name — nothing to fix |
| Live Pages site | serving the **pre-rename** deck folders (`20260623-1-…`) |

So visitors never actually reach the site today; they get bounced to the repo.

## Repo side: already done

No code changes are needed. The workflow reads the domain from the repo's Pages
settings at build time, so it produces correct URLs before *and* after this
migration. Nothing in this runbook requires editing a file.

---

## 1. Commit locally

```bash
cd /Users/keith.jones/Source/UnpackThePCAP
git status
git add -A
git commit -m "Add landing page, custom domain support"
```

**Do not push yet.** Step 6 has to happen first.

## 2. DreamHost: delete the SSL certificate

DreamHost's docs are explicit that a certificate blocks the change: *"you must
delete it in order for your DNS records to be removed."* The domain does
currently serve valid HTTPS from DreamHost, so there is a cert to remove.

1. Panel → **Websites** → **Secure Certificates**
2. Find `unpackthepcap.com`
3. Delete the certificate

Nothing is lost — GitHub issues its own certificate in step 10.

## 3. DreamHost: set the domain to DNS Only

Apex `A` records are ignored while a domain is Fully Hosted, so this has to
happen before step 4.

1. Panel → **Manage Websites**
2. Click **Manage** for `unpackthepcap.com`
3. Select the **Settings** tab
4. Find **Non-Hosting Options**, expand **Set to DNS Only**
5. Click **Set to DNS Only**
6. Confirm with the red **Yes, Set to DNS Only** button

This is what retires the `.htaccess` redirect: there is no longer a web server
to run it. Hosted files are not deleted.

## 4. DreamHost: DNS records

Panel → **Manage Websites** → **DNS Settings** for `unpackthepcap.com`.

**Delete only records pointing at `69.163.176.199`** — that is the DreamHost web
server, and the apex `A` record is the only one aimed at it. Step 3 normally
clears it automatically; check for a leftover and delete it if it is still there.

**Leave every mail record alone.** The DNS list is mostly email — the `@` and
`mail` `MX` records, the `mail` / `mailboxes` / `webmail` `A` records, the
`autoconfig` `CNAME`. None of them affect GitHub Pages, and deleting them breaks
mail for the domain. Pages only cares about the apex `A`/`AAAA` records and `www`.

Nothing needs deleting on `www`: it does not exist yet, so there is no A record
to collide with the CNAME below.

**Then add** each record via **Add Record** → hover the record type → **ADD**:

| Type | Host | Points to |
|:--|:--|:--|
| A | *(leave blank)* | `185.199.108.153` |
| A | *(leave blank)* | `185.199.109.153` |
| A | *(leave blank)* | `185.199.110.153` |
| A | *(leave blank)* | `185.199.111.153` |
| AAAA | *(leave blank)* | `2606:50c0:8000::153` |
| AAAA | *(leave blank)* | `2606:50c0:8001::153` |
| AAAA | *(leave blank)* | `2606:50c0:8002::153` |
| AAAA | *(leave blank)* | `2606:50c0:8003::153` |
| CNAME | `www` | `keithjjones.github.io` |

A blank Host field means the root domain. **No trailing dot** on the CNAME value
— the panel rejects `keithjjones.github.io.` as "Invalid domain name," since it
qualifies the name itself. (`dig` output in step 5 *does* show the trailing dot;
that is normal and not a mismatch.)

The `AAAA` records are optional and only add IPv6. Addresses are from
[GitHub's apex domain docs](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site);
check there if this is ever redone, in case they have changed.

`www` points at **`keithjjones.github.io`, not at `unpackthepcap.com`.** GitHub
warns that if a custom subdomain references the apex domain "you will encounter
issues with enforcing HTTPS to your website," because certificates are issued
per name.

## 5. Verify DNS

```bash
dig +short unpackthepcap.com A
dig +short unpackthepcap.com AAAA
dig +short www.unpackthepcap.com
```

Wait for:

- apex `A` → the four `185.199.x.153` addresses
- apex `AAAA` → the four `2606:50c0:800x::153` addresses, if added
- `www` → `keithjjones.github.io.` followed by the Pages IPs

Do not continue while the apex still shows `69.163.176.199`.

## 6. GitHub: set the custom domain

1. Open `https://github.com/keithjjones/UnpackThePCAP/settings/pages`
2. Under **Build and deployment**, confirm **Source** is **GitHub Actions**
3. Under **Custom domain**, enter `unpackthepcap.com` — apex only, do **not**
   add a separate `www` entry
4. **Save**

It will show "DNS check in progress," then a green check.

**This must come before the push.** The workflow reads `base_path` from this
setting, and the decks bake that prefix into their HTML as absolute asset URLs.
Set the domain first and they build with the correct empty prefix on the first
run; push first and they build with `/UnpackThePCAP/`, which 404s on the new
domain and renders a blank page until the workflow is re-run.

No `CNAME` file is involved. GitHub's docs state that for Actions-based
deployments "no `CNAME` file is created, and any existing `CNAME` file is
ignored and is not required."

## 7. Push

```bash
git push origin main
```

## 8. Watch the build

Open `https://github.com/keithjjones/UnpackThePCAP/actions` and follow the run:
Setup Pages → three decks → landing page → deploy. A couple of minutes.

In the **Build All Decks** log, each `--base` should read `"/260623-…/"` with
**no** `/UnpackThePCAP` prefix. If the prefix is there, step 6 did not take —
fix it and re-run the workflow.

## 9. Verify the live site

```bash
curl -sSI https://unpackthepcap.com/ | head -1
curl -sSI https://www.unpackthepcap.com/ | head -2
curl -sSI https://unpackthepcap.com/260623-ClickFix-Unknown-RAT-Netsupport/ | head -1
```

Expect `200` on the apex, a `301` from `www` to `https://unpackthepcap.com/`,
and `200` on the deck.

Then **open the site and click a deck through to an actual slide.** This is the
check that matters: a deck built with the wrong base path still returns `200`
and renders a blank page, so status codes alone will not catch it. Try the
search box and the `/` shortcut while you are there.

## 10. Enforce HTTPS

Settings → Pages → tick **Enforce HTTPS**.

GitHub's docs say up to an hour for the certificate, and that the checkbox
itself "can take up to 24 hours" to become available. If it is still greyed out
after that, remove the custom domain, Save, re-add it, Save.

## 11. Fix the YouTube description links

The currently-deployed decks use the **pre-rename** folder names — as of this
writing `…/20260623-1-ClickFix-Unknown-RAT-Netsupport/` returns `200` and the
new `260623-…` name does not exist yet. After the push it is the other way
round, so any link using an old name breaks.

Update the descriptions to:

- **Ep 1** → `https://unpackthepcap.com/260623-ClickFix-Unknown-RAT-Netsupport/`
- **Ep 2** → `https://unpackthepcap.com/260730-Polish-Powiadomienie-JS-Campaign/`

Old `github.io` links redirect to the custom domain and preserve the path after
the repo name, so they keep working in general — but no redirect can rescue a
folder that was renamed.

---

## Troubleshooting

| Symptom | Cause |
|:--|:--|
| DreamHost will not set DNS Only | SSL certificate still present — step 2 |
| Panel rejects the apex `A` records | Domain still Fully Hosted — step 3 |
| Apex still resolves to `69.163.176.199` | Leftover custom A record — step 4 |
| Site loads but decks are blank pages | Decks built with the old base; step 6 landed after the push. Re-run the workflow |
| Pages says "domain does not resolve" | DNS not propagated yet; recheck step 5, then Save again |
| Enforce HTTPS greyed out after 24h | Remove and re-add the custom domain |
| `www` does not redirect | `www` CNAME missing, or aimed at the apex instead of `keithjjones.github.io` |
| HTTPS never provisions | A `CAA` record was added that omits `letsencrypt.org` (there are none today) |
