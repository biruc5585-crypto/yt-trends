# YouTube Trends Tracker (business economics niche)

Ye GitHub par **din mein 3 baar apne aap** chalta hai (aapka PC band ho tab bhi).
Har baar YouTube se aapke niche ke pichhle 10 din ke videos laata hai aur
`data/youtube-trends.md` mein 3 list banata hai:

- **A.** Pichhle 10 din ke sabse viral
- **B.** Abhi tezi se badh rahe (pichhle ~24 ghante ki speed)
- **C.** Bilkul naye (48 ghante ke andar)

Aapka Claude plugin "topic do" bolne par yahi file padh kar topic deta hai.

---

## Setup (sirf ek baar, lagbhag 10 minute)

### 1. Repository banao
1. github.com par login karo.
2. Upar daayein **+** → **New repository**.
3. Repository name: **`yt-trends`** (yahi naam rakhna, plugin isi naam ko dhoondhta hai).
4. **Public** chuno. (Isme sirf YouTube ka public data hai. Aapki API key Secrets mein chhupi rehti hai, public repo mein bhi koi nahi dekh sakta.)
5. "Add a README file" par tick **mat** lagao. **Create repository** dabao.

### 2. Files upload karo
1. Is ZIP ko apne computer par unzip karo. Ek folder banega `yt-trends-tracker`.
2. GitHub par naye repo ke page par **"uploading an existing file"** link dabao.
3. `yt-trends-tracker` folder ke **andar** ki saari cheezein (`.github` folder, `data` folder, `tracker.py`, `niche-queries.txt`, `channels.txt`, `README.md`) utha kar wahan drag karo.
   - `.github` folder zaroor jaana chahiye. Na dikhe to Windows Explorer mein **View → Show → Hidden items** on karo.
4. Neeche **Commit changes** dabao.

### 3. API key ko Secret mein daalo
1. Repo mein **Settings** → baayein **Secrets and variables** → **Actions**.
2. **New repository secret** dabao.
3. Name: `YOUTUBE_API_KEY`
4. Secret: apni YouTube API key paste karo. **Add secret** dabao.

### 4. Pehli baar chalao
1. Repo mein upar **Actions** tab kholo. Agar "I understand my workflows, go ahead and enable them" dikhe to dabao.
2. Baayein **YouTube trends** chuno → daayein **Run workflow** → **Run workflow**.
3. 1-2 minute baad hara ✓ aayega. `data/youtube-trends.md` kholo — list ban gayi hogi.

Bas. Ab ye din mein 3 baar khud chalega. "Abhi tezi se badh rahe" wali list 2-3 run (lagbhag 1 din) ke baad poori bharegi.

---

## Badalna ho to
- **Apne competitor channels track karne hain:** `channels.txt` kholo → pencil (edit) → har line mein ek channel link (`https://www.youtube.com/@naam`) → Commit.
- **Search queries badalni hain:** `niche-queries.txt` edit karo.
- **10 ki jagah 15 din:** `.github/workflows/youtube-trends.yml` mein `TRACK_DAYS: "10"` badlo.

## Dikkat aaye to
- Actions mein laal ✗ → us run par click karo, error padho. `NO_KEY` = Secret ka naam galat hai (bilkul `YOUTUBE_API_KEY` hona chahiye).
- `quota` wali error = us din ki free limit khatam. Agle din apne aap theek.
- Key leak ho jaye: Google Cloud → Credentials mein purani delete, nayi banao, Secret update karo. Channel ko koi khatra nahi.
