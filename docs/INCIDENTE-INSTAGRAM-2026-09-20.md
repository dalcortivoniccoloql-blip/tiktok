<!-- Durata: LEGATO-A:P09 -->

# 🔴 Incidente Instagram — 2026-09-20 → ✅ chiuso 2026-09-23

> Copia sincronizzata via git del record che sta in `faceless-shorts/docs/SETUP_INSTAGRAM.md` del workspace P09 (quella copia vive su Drive, oggi in pausa: questa è l'unica che tutti vedono).


> **Durata:** LEGATO-A:P09 · aperto il 2026-09-22, **sbloccato il 2026-09-23** (Niccolò). ⚠️ **Causa mai identificata**: si è risolto da solo. Non trattare le ipotesi come diagnosi.

## ✅ ESITO — si è sbloccato da solo, con lo STESSO token (2026-09-23)

**L'accesso API è tornato senza che nessuno abbia toccato niente.** Run diagnostico `35823125958` (2026-09-23 05:36 UTC):

```
--- graph.instagram.com /me ---
HTTP 200 OK
{"id":"28547559528213837","username":"5absurdfacts_ql","account_type":"BUSINESS"}
```

🔑 **Il token è lo STESSO di prima**, e questo è il punto che vale più di tutto il resto:
- il secret `IG_ACCESS_TOKEN` porta ancora la data **2026-09-19T10:28:56Z** — **non è mai stato riscritto** (nessun `ig_setup.py` eseguito);
- lunghezza del token **181 caratteri** sia nel run fallito del 22/09 sia in quello riuscito del 23/09.

➡️ **Non era il token, non era l'app, non era l'account.** Era un **blocco temporaneo lato Meta**, durato **~2 giorni e 10 ore**: dal 2026-09-20 ~19:14 UTC al più tardi 2026-09-23 05:36 UTC (si è sbloccato tra il 22/09 19:58 UTC — ultimo run di pubblicazione ancora bloccato — e il 23/09 05:36 UTC).

**Costo:** ~7 Reel non pubblicati. YouTube non si è mai fermato.

### ⛔ L'esclusione che avevo sbagliato

Avevo scritto: *"❌ Non è transitorio: ~8 run falliti su 2 giorni, non un 429/5xx."* **Era falso.** Era esattamente transitorio — solo su una scala di **giorni**, non di minuti, e senza mai passare da un 429. **Lezione:** "ho visto fallire N volte di fila" misura la **durata osservata finora**, non la natura del guasto. Per dichiarare non-transitorio serve un meccanismo che spieghi *perché* non può rientrare da solo — qui non c'era.

### ✅ Il test di controllo su `debug_token`, finalmente fatto

Nel run riuscito, con l'API perfettamente funzionante, `debug_token` risponde **comunque** con un errore — ma **diverso**:

```
HTTP 403 · message: Application does not have permission for this action
type: IGApiException · code: 10
```

➡️ Conferma definitiva che **quell'endpoint non è utilizzabile così su `graph.instagram.com`**, a prescindere dallo stato del token: il "fallisce perfino `debug_token`" del 22/09 non provava niente, come già ritirato. **Da togliere dal workflow diagnostico**: genera solo rumore.

### 🔴 Cosa resta da fare (il guasto è chiuso, il problema di disegno no)

1. **Verificare su un artefatto, non sul verde del run** (regola già cablata in `CLAUDE.md` dopo il fermo del 26/08): il prossimo run di pubblicazione utile è alle **07:00 UTC**. "Riparato" = **Reel effettivamente online sul profilo**, non `HTTP 200` su `/me`.
2. **Un fallimento Instagram lascia il run VERDE** — è la ragione per cui nessuno se n'è accorto per 2 giorni e mezzo. `cloud_publish.py` tratta IG come best-effort dopo YouTube. Serve almeno un segnale (run rosso dopo N fallimenti IG consecutivi, o un contatore). **È la stessa famiglia del fermo del 26/08 e della soglia del 01/09: un ramo che significa "il prodotto non esce" non deve uscire verde.**
3. **`ig-token-reminder.yml` va corretto**: ha gridato *"Token NON valido → rigenera"* per 2 giorni su un token perfettamente valido. Se qualcuno gli avesse dato retta, avrebbe rigenerato il token senza risolvere niente e avrebbe dato la colpa alla cosa sbagliata.
4. **Rimuovere `ig-diagnostica.yml`** quando non serve più (o tenerlo, togliendo la chiamata a `debug_token`).

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
- ❌ **Non è un permesso di pubblicazione né l'endpoint dei Reel.** Fallisce anche `GET /me?fields=username`, la lettura più banale che esista.
- ⛔ **RITIRATO nella stessa sessione — non usare come prova.** Avevo scritto *"fallisce perfino `debug_token`, quindi è a monte del token"*. **Non prova niente:** la chiamata era `debug_token?input_token=TOK&access_token=TOK`, cioè **autenticata con lo stesso token sotto esame** — se quel token è morto, fallisce per quel motivo e basta. (Su `graph.instagram.com` `debug_token` vuole per giunta un *app access token*, non un user token: la chiamata era malformata comunque.) Stessa lezione del 23/08 sui commenti disattivati: **serviva un test di controllo su un caso di risposta nota**, e non l'avevo fatto. Tolto dalla lista delle esclusioni.
- ❌ **Non è transitorio**: ~8 run falliti su 2 giorni, non un 429/5xx.

**Cosa dice il codice `200` — e cosa NON dice.** Nella tassonomia Meta `code: 200` è la famiglia **permesso/accesso**, mentre un token scaduto o revocato è di norma **`190`**, che qui non compare. È un **indizio** a favore di un blocco app/account, **non una prova**: Meta restituisce codici di famiglia permesso anche per token invalidati da un'azione di enforcement. Senza un test di controllo, `code: 200` è una stringa letta come se fosse uno stato.

**Test di controllo che manca (l'unico rimasto).** Generare un token **nuovo** dal pannello (*Configurazione dell'API con Instagram Login* → sezione 2 → **Genera token** accanto a `5absurdfacts_ql`) e riprovare. È binario: token nuovo **ancora bloccato** → è davvero app/account · token nuovo **valido** → era il token, e il rimedio è `py -3 tools/ig_setup.py --solo-secret`. Finché questo test non è fatto, la causa **non è identificata**.

### Cosa è stato verificato a schermo sul pannello Meta (2026-09-22, sessione Claude in Chrome)

Tutto integro — **nessuna delle ipotesi "blocco visibile" regge**:

| Controllato | Esito |
|---|---|
| Banner/avviso sulla dashboard dell'app | **nessuno** |
| *Azioni richieste* | **nessuna** (reindirizza alla dashboard) |
| *Avvisi della posta* (inbox avvisi dell'app) | **vuota**, 0 messaggi |
| Caso d'uso *Gestisci i messaggi e i contenuti su Instagram* | presente e **spuntato verde** |
| Permessi `instagram_business_basic` / `instagram_business_content_publish` | **entrambi presenti**, stato *Pronta per il test*, 56 e 53 chiamate API |
| *Ruoli dell'app* | `Niccolò Dal Cortivo` Amministratore + `5absurdfacts_ql` **Tester di Instagram** |
| Account IG collegato in *Configurazione API* | `5absurdfacts_ql` (`17841424481091263`), ancora lì |
| IG → *App e siti web* | app `5AbsurdFacts Publisher-IG` **Attiva**, autorizzata 19/09; invito test **attivo** |
| IG → *Account per professionisti* | **ancora professionale**, categoria *Media* → **non** è tornato Personal |
| Profilo `@5absurdfacts_ql` | vivo, **5 post** ancora pubblicati, nessuna rimozione di contenuti |
| **Registro attività dell'app** | **fermo al 19/09** (creazione + permessi). **Nessuna modifica il 20/09.** |

➡️ **Conseguenza importante:** nessuno ha cambiato la configurazione dell'app nella finestra del guasto. Ma il registro attività **non registra la generazione dei token** — quindi un click su *Genera token* domenica pomeriggio farebbe morire in silenzio quello salvato nel secret **senza lasciare traccia in nessuna delle schermate qui sopra**. È l'unica ipotesi che spiega *insieme* la finestra di 7 ore e il pannello immacolato.

**Ipotesi aperte, in ordine di plausibilità — nessuna verificata:**
1. **Enforcement automatico di Meta** su un'app di **2 giorni** (creata il 19/09) che ha iniziato subito a pubblicare 3×/giorno — un blocco di questo tipo **non compare nel pannello**, il che è coerente con tutto ciò che si è visto.
2. **Il token salvato nel secret è stato invalidato** da qualcos'altro (un token nuovo invalida il precedente, e il registro attività non lo mostra). ⚠️ **Declassata dal 1° posto il 22/09**: l'owner conferma di **non aver toccato pannello né account** domenica pomeriggio, quindi non per un *Genera token* fatto a mano.
3. ~~L'account IG riportato a Personal/Creator, o ruolo tester tolto~~ → **ESCLUSO a schermo il 22/09** (tabella sopra).

⛔ **Perché il test di controllo non è stato fatto in sessione:** cliccando *Genera token* dalla sessione AI **non succede nulla di visibile** — nessun dialog, nessuna scheda nuova nel gruppo controllato dall'AI (non è stato verificato *perché*: popup bloccato, finestra fuori dal gruppo, o altro). Il passo va fatto **a schermo dall'owner**.
3. Restrizione dell'app per verifica business / App Review non completata.

**🐛 Bug trovato di passaggio (in strumento nostro, non di Meta).** `.github/workflows/ig-token-reminder.yml` etichetta **qualunque** HTTP 400 come *"Token Instagram NON valido"* e consiglia `ig_setup.py --solo-secret`: il titolo è scritto a mano nella funzione `fail()`, non deriva dalla risposta di Meta. In questo incidente manda dritti sulla strada sbagliata. **Da correggere: stampare il messaggio reale di Meta invece di affermare una causa.** (Separato dall'incidente, non risolverlo insieme.)

**Strumento diagnostico.** `.github/workflows/ig-diagnostica.yml` sul repo `dalcortivoniccoloql-blip/tiktok` (`workflow_dispatch`, usa-e-getta): interroga `/me`, `/{IG_USER_ID}` e `debug_token` e stampa `code`/`error_subcode`/`fbtrace_id` completi. Il body d'errore **non contiene il token**, è sicuro loggarlo. Rilanciarlo dopo ogni tentativo di fix sul pannello Meta per sapere se è passato; rimuoverlo a incidente chiuso.
