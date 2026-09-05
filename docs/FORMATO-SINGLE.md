> **Proprieta:** 🟢 Zona P09 — modulo `faceless-shorts/` (owner Niccolò).
> **Durata:** LEGATO-A:P09

# 🎬 Formato "single" — 1 fatto per Short (v3, 2026-08-23)

> **In una riga:** il formato a 5 fatti in 22 secondi è stato misurato e non regge la ritenzione. Questo documento definisce il formato che lo sostituisce, perché è fatto così, e come si misura se funziona.

## 1. Perché si cambia (i numeri, non le opinioni)

Dall'analisi del canale del 2026-08-23 ([`ANALISI-CANALE-2026-08-23.md`](ANALISI-CANALE-2026-08-23.md)) + YouTube Studio → Analytics → Contenuti, ultimi 28 giorni:

| Metrica | Canale (formato a 5 fatti) | Benchmark pubblico |
|---|---|---|
| **Ha continuato a guardare** (viewed vs swiped away) | **42,1%** | **70-90%** = distribuzione forte · **<60%** = collasso |
| Views dal **feed Shorts** | **12,2%** (~11 views in 28 gg su 41 video) | il feed è l'unica superficie che scala |
| Views dalla **ricerca** | 78,9% | coda lunga, non scala |
| Visione media | **~8 s su ~23 s** | — |

**Fonti dei benchmark** (raccolte il 2026-08-23):
- [virvid.ai — *The First 3 Seconds: Hook Structures That Stop Scroll on Shorts*](https://virvid.ai/blog/first-3-seconds-hook-faceless-shorts-2026): 70-90% VVSA = distribuzione forte; **sotto il 60% la distribuzione collassa**; >40% di swipe = hook fallito; prima parola parlata **entro mezzo secondo**; caption **dal primo fotogramma**.
- [opus.pro — *YouTube Shorts Hook Formulas That Drive 3-Second Holds*](https://www.opus.pro/blog/youtube-shorts-hook-formulas): hook completo in **2-2,5 secondi**; primo frame **ad alto contrasto, mai scuro o affollato**; testo a schermo grande e leggibile (60% guarda **senza audio**).
- [opus.pro — *The Ideal YouTube Shorts Length & Format for Retention*](https://www.opus.pro/blog/ideal-youtube-shorts-length-format-retention): sweet spot **15-30 s**; **50-60% di chi abbandona lo fa nei primi 3 secondi**; **un cambio visivo ogni 2-4 secondi**; finale che rientra nel loop; caption impresse = +15-25% di ritenzione.

⚠️ Sono fonti di settore (creator economy), non paper: valgono come **ordine di grandezza e direzione**, non come verità esatta. Il numero che conta davvero resta il nostro, in Studio.

**La diagnosi che ne esce:** 5 fatti in 22 secondi = ~4 secondi a fatto. Nessuno dei cinque ha lo spazio per incuriosire, il video apre con un hook **identico per tutti i video** ("5 absurd facts, you won't believe the last one"), e dopo il primo fatto non c'è **nessun motivo di restare**. Non è un problema di distribuzione: è quello che succede quando il primo secondo non promette niente di specifico.

## 2. Com'è fatto uno Short "single"

```
HOOK      0,0 - 2,5 s   una frase, specifica, tutta a schermo insieme
BEAT 1    2,5 - 6 s     l'ambientazione del fatto
BEAT 2    6 - 11 s      il meccanismo (il "perché" o il "come")
BEAT 3    11 - 17 s     il payoff: il dettaglio più assurdo, alla fine
(nessun outro parlato: la coda rompe il loop)
```

Regole cablate nel codice, non da ricordare a memoria:

| Regola | Dove vive | Perché |
|---|---|---|
| Hook a schermo **intero** (non a chunk da 3 parole) per i primi ~2,5 s | `SINGLE_HOOK_FULL_TEXT` + `_load_timeline()` | A chunk, a mezzo secondo si legge un terzo della promessa: sound-off non si capisce cosa stai promettendo |
| Primo frame **più luminoso** (0,95 invece di 0,78) | `HOOK_BG_DARKEN` in `_make_frame()` | "mai aprire su un frame scuro": è il frame che decide lo swipe |
| **Stacco di sfondo a ogni beat** (~1 ogni 3-4 s) | `BEAT_CUT_ENABLED` / `BEAT_CUT_JUMP_S` | Prima l'inquadratura era identica per 22 secondi. Costo zero: salta il punto del clip di sfondo, non monta clip nuovi |
| **Niente outro parlato** | `cta_text()` → `""` nel formato single | Il "Follow for more" allunga la coda e rompe il loop; l'invito resta in descrizione e nel footer impresso |
| Titolo = **l'hook**, non un template | `build_title()` | L'hook è già scritto per fermare lo scroll; e "and 4 more ABSURD facts" su un video con **un** fatto è una promessa falsa |
| Descrizione/caption = hook + fatto per esteso | `build_description()` / `build_caption()` | La ricerca porta il 78,9% delle views: il testo resta pieno di parole reali |

**Compatibilità:** uno script **senza** `"format": "single"` continua a comportarsi esattamente come prima (verificato: render dello script 116, `formato 5 fatti (v2) - sottotitoli sincronizzati`). Le due strade convivono.

## 3. Schema di uno script

```json
{
  "format": "single",
  "hook":  "There is a penguin with a real army rank.",
  "facts": [
    "His name is Sir Nils Olav and he lives in a zoo in Scotland.",
    "The King's Guard of Norway made him their mascot, then knighted him in two thousand and eight.",
    "Every few years the soldiers come back, line up, and give him a higher rank."
  ],
  "cta": ""
}
```

⚠️ **Il campo si chiama ancora `facts` ma contiene i BEAT di un unico fatto**, non 5 fatti diversi. È voluto: mantiene identici timeline, caption e render. Il nome è brutto, la compatibilità vale di più.

### Come si scrive un hook che regge

1. **Massimo 8-9 parole** (≈2,5 s di TTS a `+8%`). Più lungo = la promessa arriva dopo il momento in cui la gente decide.
2. **Una sola affermazione, concreta e verificabile.** «Wombats poop in perfect cubes» — non «Some animals have strange habits».
3. **Deve creare un buco informativo**, non riassumere: dopo l'hook lo spettatore deve volere il *perché*.
4. **Inglese A2-B1** (regola di canale del 2026-08-12): niente parole difficili, niente subordinate, unità **scritte per esteso** ("centimeters", non "cm" — il TTS le leggerebbe male).
5. **Funziona anche come titolo YouTube**, perché è lo stesso testo.
6. **Il payoff sta nell'ultimo beat**, e se possibile rimanda all'hook: il video rientra nel loop.

## 4. Come si misura se ha funzionato

**La metrica è il coinvolgimento, non le views.** Studio → Analytics → **Contenuti** → *Coinvolgimento degli spettatori*:

| Cosa guardare | Valore di partenza (28 gg al 23/08, formato a 5 fatti) | Obiettivo |
|---|---|---|
| **Ha continuato a guardare** | **42,1%** | >60% = si esce dalla zona di collasso · 70%+ = distribuzione |
| Quota di views dal **feed Shorts** | 12,2% | in salita = il feed sta iniziando a servire i video |
| Views/video | 2,4 | conseguenza, non causa: non usarla per decidere |

**Come leggere il confronto, onestamente:**
- Il 42,1% è un **aggregato di canale su 28 giorni**, non un dato per-video. Il confronto giusto è la **VVSA del gruppo dei 10 nuovi** dopo qualche giorno di dati, non il numero di un singolo video il giorno dopo.
- A 3 video al giorno, i 10 escono in **~3-4 giorni**; i dati si assestano in altri 3-4 → **prima lettura utile ~1 settimana dopo l'accensione**, non prima.
- Se la VVSA sale ma le views no: sta funzionando comunque, il feed reagisce con ritardo. Se **non sale**, il problema non è il formato — e a quel punto la domanda torna a essere se questo canale valga altro tempo.

## 5. Stato — cosa è già fatto e cosa manca

✅ **Fatto il 2026-08-23:**
- Codice in **tutte e tre le copie** (Drive · `dev/faceless-shorts-v2` · deployed `Desktop/tiktok`), verificate identiche file per file dopo la copia.
- 10 script nuovi in `pipeline/english_scripts_4.json` → numeri **200-209** (la numerazione è posizionale: i file si concatenano in ordine alfabetico, quindi il `_4` si accoda dopo il 199).
- **2 render di prova** verificati **sui pixel** (non sull'exit code): hook intero leggibile a 0,3 s, sfondo chiaro, footer `@5AbsurdFacts-ql`, stacco visibile a ogni beat, `sottotitoli sincronizzati`. Durata 16 s.
- **Regressione verificata**: lo script 116 (vecchio formato) renderizza come prima.
- Fix del bug `#Short` (puntini di sospensione contati dentro il limite dei 100 caratteri).

- ✅ **Pushato sul repo `tiktok`** (decisione dell'owner, 23/08): commit [`e7b04e9`](https://github.com/dalcortivoniccoloql-blip/tiktok/commit/e7b04e9), **verificato rileggendo i file dall'API GitHub**, non da `git status`. Il push ha richiesto un `git pull --rebase`: il checkout locale era **19 commit indietro** (tutti del bot, solo `state.json`) — è la stessa staleness già trovata il 16/08, e va messa in conto ogni volta che si tocca questo repo.
- ⚪ **Il push è inerte per gli spettatori**: gli script 116-199 non hanno il campo `format`, quindi il cron continua a pubblicare nel vecchio formato finché `state.json` non si sposta.

- ✅ **ACCESO il 2026-08-23** dopo che l'owner ha visto i render: `state.json` **117 → 200** (commit [`a3b9e0f`](https://github.com/dalcortivoniccoloql-blip/tiktok/commit/a3b9e0f)).
- ✅ **Primo single pubblicato davvero**, con un run lanciato a mano per verificarlo subito invece di aspettare lo slot: [`youtu.be/eJrzgyLEksc`](https://youtu.be/eJrzgyLEksc) — log del run: `formato single (1 fatto) - sottotitoli sincronizzati - hook intero fino a 2.5s` · `privacyStatus=public` · **`VERDETTO: MATCH`** (canale giusto) · contatore avanzato a **201**. Pagina pubblica riletta con `yt-dlp`: titolo *"There is a penguin with a real army rank #Shorts"*, **16 s**, `media_type=short`, categoria Education. Il ramo Instagram si è autoescluso come previsto (secret non configurati).

⏳ **Non fatto, richiede una decisione:**
- Riscrivere gli 84 script in coda nel formato single, se il test va bene.
- **Opzione aperta, non implementata:** far **fallire** il run invece di degradare quando il sidecar dei tempi non è valido. Oggi il codice cade sui sottotitoli "a stima" (desincronizzati) stampando una nota nel log — e nel cloud il log non lo legge nessuno. Un run rosso costa un video, dieci video con le caption fuori sync costano il test.

### 2026-08-31 — i 10 sono usciti tutti, e la coda è finita con loro

**Cosa è successo davvero:** i 10 script single (200-209) sono stati pubblicati tra il **23 e il 26 agosto** — tutti e dieci, verificati sulla pagina pubblica del canale. Erano anche gli **ultimi 10 script esistenti**: il #209 era l'ultimo dei 209 in archivio. Dal 26/08 il cron ha girato 3 volte al giorno **restando verde senza pubblicare niente**, perché `cloud_publish.py` a coda vuota faceva `return 0`. Cinque giorni di fermo, zero segnali.

| | |
|---|---|
| Ultimo video pubblicato | `Chess has more games than the universe has atoms`, **2026-08-26** (script #209) |
| Contatore remoto | `{"next": 210}` — fermo, perché non c'era niente da consumare |
| Gruppo di test completo | ✅ i 10 single sono tutti pubblici, usciti in 4 giorni come previsto |
| Coda al 31/08 | **30 script nuovi** (210-239), formato single, ~10 giorni a 3/giorno |

**Tre cose cambiate perché non si ripeta** (dettaglio in [`../../CLAUDE.md`](../../CLAUDE.md) § "Il fermo silenzioso del 2026-08-26"):
1. **Coda vuota = run rosso** quando la pubblicazione è accesa. Un guasto che ferma il canale deve produrre un'email, non una riga di log.
2. **Il generatore produce lo schema single.** Fino al 31/08 generava ancora `[{"facts": [...×5]}]`: rifornire con quello avrebbe riportato il canale al formato a 5 fatti **un video alla volta e in silenzio**, perché uno script senza `"format": "single"` si renderizza come prima (§ 3). È la trappola peggiore delle tre: si sarebbe vista solo nei numeri, settimane dopo.
3. **2 test permanenti** in `../tests/`, senza rete né ffmpeg: coprono i 4 rami di `cloud_publish` e la validazione del generatore.

⏳ **La lettura VVSA dei 10 è ancora da fare** (era prevista ~31/08). Il gruppo di test è **pulito** proprio perché la coda si è svuotata: i 10 single sono usciti tutti insieme e dopo di loro non è uscito nient'altro. Va letta **prima** che i 30 nuovi comincino a mescolarsi nell'aggregato di canale — Studio → Analytics → Contenuti → *Coinvolgimento degli spettatori*, confronto contro il **42,1%** di § 4. Serve Studio a schermo: il token dell'API ha solo lo scope `youtube.upload` e non può leggere le analytics.

## 6. Fatti riusati — da sapere

**7 dei 10 fatti erano già usciti** come *una riga dentro un video a 5 fatti* (verificato con un match sul corpus, non a memoria):

| Nuovo script | Fatto già uscito in | Testo di allora |
|---|---|---|
| 201 octopus | script **8** (pubblicato) | *"Octopuses have three hearts."* |
| 202 Venus | script **9** (pubblicato) | *"A day on Venus lasts longer than a year on Venus."* |
| 203 Torre Eiffel | script **84** (pubblicato) | *"The Eiffel Tower grows about 15 centimeters taller in summer…"* |
| 204 Cleopatra | script **52** (pubblicato) | *"Cleopatra lived closer in time to the Moon landing than to the pyramids."* |
| 205 Antartide | script **23** (pubblicato) | *"The largest desert in the world is Antarctica."* |
| 207 Oxford | script **52** (pubblicato) | *"Oxford University is older than the Aztec Empire."* |
| 209 scacchi | script **57** (pubblicato) | *"There are more possible chess games than atoms in the universe."* |

**Nuovi di zecca:** 200 (pinguino Sir Nils Olav), 206 (Pringles), 208 (tartarughe).

**Perché va bene lo stesso, ma va detto:** quei video hanno avuto **0-2 views** — il fatto non l'ha visto nessuno, e lì era una riga di 4 secondi mentre qui è un video di 17. Per un test sul **formato** è anche coerente: cambia la confezione, non l'ingrediente. Se però si preferisce partire con 10 fatti mai usati, si rigenera il file: è mezz'ora, non un problema tecnico.

⚠️ **Se un giorno si riprende la vecchia coda:** lo **script 126** (Venus, ancora non pubblicato) diventerebbe un doppione vero del 202 → va saltato o riscritto.
