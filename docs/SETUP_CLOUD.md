# Setup Cloud — pubblicazione 100% automatica (PC spento)

Con questo setup, GitHub pubblica **3 Short al giorno da solo**, anche con il tuo
PC completamente spento. Si fa **una volta sola**, poi non tocchi più niente.

Tempo richiesto: ~20 minuti.

---

## Cosa fa il sistema

- Ogni giorno alle **09:00, 14:00 e 19:00** (ora italiana) genera e pubblica 1 Short
- Tiene il conto di quale script tocca (file `state.json`)
- Quando i contenuti stanno per finire, ne genera di nuovi da solo (se attivi l'API Claude)

---

## PASSO 1 — Crea un account GitHub (se non ce l'hai)

1. Vai su [github.com](https://github.com) → **Sign up**
2. Crea l'account (gratis)

## PASSO 2 — Installa GitHub Desktop

1. Scarica da [desktop.github.com](https://desktop.github.com)
2. Installalo e accedi con il tuo account GitHub

## PASSO 3 — Carica il progetto su GitHub

1. In GitHub Desktop: **File → Add Local Repository**
2. Scegli la cartella `C:\Users\nicco\Desktop\tiktok`
3. Se dice "this is not a git repository", clicca **"create a repository"**
4. Lascia i campi come sono → **Create Repository**
5. In alto clicca **Publish repository**
6. IMPORTANTE: lascia spuntato **"Keep this code private"** → **Publish**

> Il file `.gitignore` esclude automaticamente i tuoi video grandi e i file segreti.
> Viene caricato solo il codice + il video di sfondo.

## PASSO 4 — Aggiungi il token YouTube come "segreto"

Il sistema deve potersi collegare al tuo YouTube, in modo sicuro.

1. Apri il file `C:\Users\nicco\Desktop\tiktok\yt_token.json` con il Blocco note
2. **Copia tutto** il contenuto (Ctrl+A, Ctrl+C)
3. Sul sito [github.com](https://github.com), apri il tuo repository `tiktok`
4. Vai su **Settings** (in alto) → menu a sinistra **Secrets and variables → Actions**
5. Clicca **New repository secret**
6. Nome: `YT_TOKEN`
7. Secret: **incolla** il contenuto copiato → **Add secret**

## PASSO 5 — Attiva i workflow

1. Sempre sul sito, apri la scheda **Actions** del repository
2. Se vedi un avviso "Workflows aren't being run", clicca **"I understand... enable"**
3. Fatto! Da ora pubblica da solo 3 volte al giorno.

### Test immediato (facoltativo)
1. Scheda **Actions** → **Publish YouTube Short** (a sinistra)
2. Clicca **Run workflow → Run workflow**
3. Dopo 2-3 minuti vedrai un check verde e il nuovo Short sul tuo canale

---

## OPZIONALE — Generazione automatica di nuove curiosità

Hai 79 script = ~26 giorni. Per non finire MAI i contenuti, attiva l'auto-generazione:

1. Procurati una API key su [console.anthropic.com](https://console.anthropic.com)
   (richiede un piccolo credito, ~1$ basta per mesi)
2. Su GitHub: **Settings → Secrets and variables → Actions → New repository secret**
3. Nome: `ANTHROPIC_API_KEY` — Secret: la tua chiave → **Add secret**

Ogni lunedì il sistema controllerà e genererà nuove curiosità se stanno per finire.
Senza questa chiave, il sistema funziona comunque fino all'esaurimento degli script.

---

## Come controllare che funzioni

- Scheda **Actions** del repository: ogni esecuzione ha un check verde (ok) o rosso (errore)
- Cliccando su un'esecuzione vedi i log dettagliati
- Il file `state.json` mostra il numero del prossimo script

## Come fermare tutto
- Scheda **Actions** → **Publish YouTube Short** → **"..."** → **Disable workflow**

## Per cambiare gli orari
- Modifica `.github/workflows/publish.yml` (righe `cron:`). Gli orari sono in UTC
  (ora italiana estiva = UTC + 2). Esempio: `0 7 * * *` = 09:00 italiane.

---

## PROBLEMA: gli Short smettono di pubblicarsi dopo ~7 giorni (`invalid_grant`)

**Causa:** se il consent screen OAuth è in modalità **"Testing"**, Google fa scadere
il refresh token ogni **7 giorni** → l'upload fallisce con
`invalid_grant: Token has been expired or revoked.`

**Fix PERMANENTE (una volta sola):**
1. Vai su [console.cloud.google.com/auth/overview](https://console.cloud.google.com/auth/overview)
2. Nella schermata consenso OAuth clicca **"Pubblica app" / "In produzione"**
   → da ora i token non scadono più (salvo revoca o 6 mesi di inutilizzo).

**Rigenerare il token (dopo il fix, o quando serve):**
1. `py pipeline\auth_youtube.py` → segui i passi nel browser → copia il refresh token
2. `py pipeline\auth_youtube.py --token "IL_TUO_TOKEN"`
   → aggiorna `yt_token.json` **e stampa il valore pronto per il secret**
3. Aggiorna il secret **YT_TOKEN** su GitHub con quel valore
   ([settings/secrets/actions](https://github.com/NdC171/tiktok/settings/secrets/actions))
4. Test: scheda **Actions** → **Publish YouTube Short** → **Run workflow**

> La pubblicazione riprende dallo `state.json` corrente: nessun doppione, nessun buco.
