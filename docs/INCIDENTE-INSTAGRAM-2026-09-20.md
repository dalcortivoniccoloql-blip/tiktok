<!-- Durata: LEGATO-A:P09 -->

# 🔴 Incidente Instagram — 2026-09-20

> Copia sincronizzata via git del record che sta in `faceless-shorts/docs/SETUP_INSTAGRAM.md` del workspace P09 (quella copia vive su Drive, oggi in pausa: questa è l'unica che tutti vedono).


> **Durata:** LEGATO-A:P09 · aperto il 2026-09-22 (Niccolò). ⚠️ **Causa esatta NON ancora identificata** — qui c'è solo ciò che è stato verificato. Non trattare le ipotesi come diagnosi.

**Sintomo.** I Reel non escono più. YouTube continua a pubblicare normalmente (3×/giorno, run verdi): l'upload IG è best-effort **dopo** YouTube in `cloud_publish.py`, quindi il run resta `success` anche quando Instagram fallisce. Nessun allarme è scattato da lì.

**Finestra del guasto — stretta a ~7 ore** (letta sui log dei run, non ricostruita):

| Run | Quando (UTC) | Esito Instagram |
|---|---|---|
| `35463306237` | 2026-09-19 19:08 | ✅ pubblicato (media `17966542356176552`) |
| `35509059505` | 2026-09-20 11:55 | ✅ pubblicato (media `17889300504614874`) — **ultimo OK** |
| `35531565611` | 2026-09-20 19:14 | ❌ `API access blocked.` — **primo KO** |
| da lì in poi | ogni run | ❌ sempre lo stesso errore |

➡️ **Si è rotto tra il 2026-09-20 11:55 e 19:14 UTC** (13:55–21:14 CEST).

**Errore completo di Meta** (letto con un workflow diagnostico `workflow_dispatch`, run `35773123319`):

```
message: API access blocked.
type:    OAuthException
code:    200
fbtrace_id: Ard6bGeTPR7GrqzPi9kCLCm
```

**Cosa è stato ESCLUSO, con prova:**
- ❌ **Non è la scadenza del token.** Secret impostato il 2026-09-19, `IG_TOKEN_EXPIRES=2026-11-18`, e ha pubblicato **due volte** dopo essere stato messo. Il token è presente e integro (181 caratteri).
- ❌ **Non è l'etichetta IA** (`is_ai_generated`, attivata il 2026-09-19): il log mostra che anche il **ritentativo senza etichetta** fallisce identico.
- ❌ **Non è un permesso di pubblicazione né l'endpoint dei Reel.** Fallisce anche `GET /me?fields=username`, la lettura più banale che esista, **e perfino `debug_token`** (endpoint di sola metadata). È a monte di qualunque operazione.
- ❌ **Non è transitorio**: ~8 run falliti su 2 giorni, non un 429/5xx.

**Cosa dice il codice `200`.** Nella tassonomia Meta `code: 200` è un **errore di permesso** (famiglia app/access), **non** un errore di token — quello è la famiglia `190`, che qui **non compare** (nessun `error_subcode`). ➡️ **Rigenerare il token non risolve**, e anzi distrugge la finestra pulita: il token attuale è la prova che il problema non è lui.

**Dove sta la causa (da verificare a schermo, azione umana).** Il pannello Meta è l'unico posto che dice *perché*: [developers.facebook.com](https://developers.facebook.com) → app **5AbsurdFacts Publisher** → cercare un **banner di avviso** in cima alla dashboard, poi *Instagram → API setup with Instagram Login* e *App Review / Permissions*. Da controllare anche la posta della mail dello sviluppatore dal 2026-09-20 in avanti (Meta manda quasi sempre una notifica quando blocca un'app) e che l'account `@5absurdfacts_ql` sia ancora **Business** e non tornato Personal/Creator.

**Ipotesi aperte, in ordine di plausibilità — nessuna verificata:**
1. Blocco automatico di Meta su un'app **nuova** (creata il 2026-09-19) che ha iniziato a pubblicare subito 3×/giorno.
2. L'account IG è stato riportato a Personal/Creator, o il ruolo tester è stato tolto.
3. Restrizione dell'app per verifica business / App Review non completata.

**🐛 Bug trovato di passaggio (in strumento nostro, non di Meta).** `.github/workflows/ig-token-reminder.yml` etichetta **qualunque** HTTP 400 come *"Token Instagram NON valido"* e consiglia `ig_setup.py --solo-secret`: il titolo è scritto a mano nella funzione `fail()`, non deriva dalla risposta di Meta. In questo incidente manda dritti sulla strada sbagliata. **Da correggere: stampare il messaggio reale di Meta invece di affermare una causa.** (Separato dall'incidente, non risolverlo insieme.)

**Strumento diagnostico.** `.github/workflows/ig-diagnostica.yml` sul repo `dalcortivoniccoloql-blip/tiktok` (`workflow_dispatch`, usa-e-getta): interroga `/me`, `/{IG_USER_ID}` e `debug_token` e stampa `code`/`error_subcode`/`fbtrace_id` completi. Il body d'errore **non contiene il token**, è sicuro loggarlo. Rilanciarlo dopo ogni tentativo di fix sul pannello Meta per sapere se è passato; rimuoverlo a incidente chiuso.
