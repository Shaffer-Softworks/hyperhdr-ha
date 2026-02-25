# Wiki source

This folder holds the wiki content so it can be edited in the repo and kept in sync with the GitHub wiki.

**To update the GitHub wiki** from here:

1. Clone the wiki repo (one-time):
   ```bash
   git clone https://github.com/Shaffer-Softworks/hyperhdr-ha.wiki.git
   cd hyperhdr-ha.wiki
   ```
2. Copy `Home.md` from this folder over `Home.md` in the cloned wiki (or copy its contents into the **Home** page).
3. Commit and push:
   ```bash
   git add Home.md
   git commit -m "Update wiki with new URLs and corrected steps"
   git push
   ```

Alternatively, on GitHub: open **Wiki** → **Home** → **Edit**, and paste in the contents of `wiki/Home.md`.

All links in this wiki point to **https://github.com/Shaffer-Softworks/hyperhdr-ha** (repo, releases, and wiki).
